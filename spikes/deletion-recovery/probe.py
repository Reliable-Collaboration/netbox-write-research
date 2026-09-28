"""Disposable NetBox 4.7.1 deletion research; NOT a production recovery service.

Run inside the named Podman lab using manage.py shell. Each test rolls back all
its database writes. Requests use Django's test client against real NetBox views,
middleware, serializers, signals, and PostgreSQL, not mocked application models.
"""

import json
import unittest
import uuid
from types import SimpleNamespace

from core.models import ObjectChange
from dcim.models import Cable, CableTermination, Device, Interface, Region, Site
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from extras.models import EventRule, Tag
from ipam.models import IPAddress
from netbox.context_managers import event_tracking
from utilities.serialization import deserialize_object

assert settings.DATABASES["default"]["HOST"] == "nbrw-audit-4-7-1-postgres", (
    "Disposable lab only"
)
assert not EventRule.objects.exists(), "Lab must have no outbound event rules"

OBSERVATIONS = []


class Probe(unittest.TestCase):
    def setUp(self):
        self.tx = transaction.atomic()
        self.tx.__enter__()
        self.client = Client()
        self.user = get_user_model().objects.get(username="audit-admin")
        self.client.force_login(self.user)
        self.prefix = "restore-" + uuid.uuid4().hex[:10]

    def tearDown(self):
        transaction.set_rollback(True)
        self.tx.__exit__(None, None, None)

    def request(self, method, path, data=None, expected=200, **headers):
        response = self.client.generic(
            method,
            "/api/" + path,
            data=json.dumps(data) if data is not None else "",
            content_type="application/json",
            **headers,
        )
        self.assertEqual(response.status_code, expected, response.content[:1200])
        return response.json() if response.content else None

    def create(self, path, data):
        return self.request("POST", path, data, expected=201)

    def site(self):
        return self.create("dcim/sites/", {"name": self.prefix, "slug": self.prefix})

    def deletion(self, model, pk):
        return ObjectChange.objects.get(
            changed_object_type__app_label=model._meta.app_label,
            changed_object_type__model=model._meta.model_name,
            changed_object_id=pk,
            action="delete",
        )

    def restore(self, change):
        # Experiment built from Apache-licensed NetBox core helpers, not Branching code.
        # This is deliberately not a general dependency planner or concurrency protocol.
        model = change.changed_object_type.model_class()
        if model.objects.filter(pk=change.changed_object_id).exists():
            raise ValueError("Original ID is occupied; never overwrite")
        data = change.prechange_data_clean
        if "tags" in data and Tag.objects.filter(name__in=data["tags"]).count() != len(
            data["tags"]
        ):
            raise ValueError("A historical tag is missing; never silently drop it")
        factory = getattr(model, "deserialize_object", None) or (
            lambda data, pk: deserialize_object(model, data, pk=pk)
        )
        decoded = factory(data, pk=change.changed_object_id)
        obj = decoded.object
        for field in obj._meta.private_fields:
            if isinstance(field, GenericForeignKey):
                ct, pk = getattr(obj, field.ct_field), getattr(obj, field.fk_field)
                if ct and pk:
                    setattr(obj, field.name, ct.get_object_for_this_type(pk=pk))
        request = SimpleNamespace(id=uuid.uuid4(), user=self.user)
        with event_tracking(request), transaction.atomic():
            obj._changelog_message = "Deletion research restore " + str(change.pk)
            obj.full_clean()
            obj.save(force_insert=True)
            for name, values in (decoded.m2m_data or {}).items():
                getattr(obj, name).set(values)
        return obj

    def device(self):
        site = self.site()
        manufacturer = self.create(
            "dcim/manufacturers/", {"name": self.prefix, "slug": self.prefix}
        )
        dtype = self.create(
            "dcim/device-types/",
            {
                "model": self.prefix,
                "slug": self.prefix,
                "manufacturer": manufacturer["id"],
            },
        )
        role = self.create(
            "dcim/device-roles/",
            {"name": self.prefix, "slug": self.prefix, "color": "ff0000"},
        )
        return self.create(
            "dcim/devices/",
            {
                "name": self.prefix,
                "site": site["id"],
                "device_type": dtype["id"],
                "role": role["id"],
            },
        ), dtype

    def test_01_rest_recreation_does_not_honor_original_id(self):
        site = self.site()
        self.request(
            "DELETE",
            f"dcim/sites/{site['id']}/",
            {"changelog_message": "accidental delete"},
            expected=204,
        )
        recreated = self.create(
            "dcim/sites/",
            {"id": site["id"], "name": site["name"], "slug": site["slug"]},
        )
        self.assertNotEqual(recreated["id"], site["id"])
        OBSERVATIONS.append(
            {
                "case": "REST explicit id",
                "original_id": site["id"],
                "new_id": recreated["id"],
            }
        )

    def test_02_api_history_is_cleaned_not_raw(self):
        site = self.site()
        self.request("DELETE", f"dcim/sites/{site['id']}/", expected=204)
        change = self.deletion(Site, site["id"])
        api = self.request("GET", f"core/object-changes/{change.pk}/")
        self.assertIn("created", change.prechange_data)
        self.assertNotIn("created", api["prechange_data"])
        OBSERVATIONS.append(
            {
                "case": "raw versus API history",
                "omitted_keys": sorted(
                    set(change.prechange_data) - set(api["prechange_data"])
                ),
            }
        )

    def test_03_original_id_tags_and_audit_restored(self):
        site = self.site()
        tag = self.create("extras/tags/", {"name": self.prefix, "slug": self.prefix})
        self.request(
            "PATCH",
            f"dcim/sites/{site['id']}/",
            {"tags": [tag["id"]], "description": "remember me"},
        )
        self.request("DELETE", f"dcim/sites/{site['id']}/", expected=204)
        change = self.deletion(Site, site["id"])
        restored = self.restore(change)
        self.assertEqual(restored.pk, site["id"])
        self.assertEqual(restored.description, "remember me")
        self.assertEqual(list(restored.tags.values_list("pk", flat=True)), [tag["id"]])
        self.assertTrue(
            ObjectChange.objects.filter(
                changed_object_id=restored.pk,
                message="Deletion research restore " + str(change.pk),
                action="create",
            ).exists()
        )
        self.assertTrue(
            ObjectChange.objects.filter(pk=change.pk, action="delete").exists()
        )
        OBSERVATIONS.append(
            {
                "case": "server-side restore",
                "same_id": True,
                "tags": True,
                "new_audit_record": True,
            }
        )

    def test_04_bare_helper_can_overwrite_occupied_id(self):
        site = self.site()
        payload = Site.objects.get(pk=site["id"]).serialize_object()
        payload["description"] = "overwritten by unsafe helper"
        deserialize_object(Site, payload, pk=site["id"]).save()
        self.assertEqual(
            Site.objects.get(pk=site["id"]).description, payload["description"]
        )
        OBSERVATIONS.append(
            {"case": "bare deserializer collision", "overwrites_existing_row": True}
        )

    def test_05_restore_guard_blocks_occupied_id(self):
        site = self.site()
        self.request("DELETE", f"dcim/sites/{site['id']}/", expected=204)
        change = self.deletion(Site, site["id"])
        self.restore(change)
        with self.assertRaisesRegex(ValueError, "occupied"):
            self.restore(change)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Site(
                id=site["id"], name=self.prefix + "-other", slug=self.prefix + "-other"
            ).save(force_insert=True)

    def test_06_missing_tag_is_silently_filtered_by_core_helper(self):
        site = self.site()
        tag = self.create("extras/tags/", {"name": self.prefix, "slug": self.prefix})
        self.request("PATCH", f"dcim/sites/{site['id']}/", {"tags": [tag["id"]]})
        self.request("DELETE", f"dcim/sites/{site['id']}/", expected=204)
        change = self.deletion(Site, site["id"])
        self.request("DELETE", f"extras/tags/{tag['id']}/", expected=204)
        decoded = deserialize_object(Site, change.prechange_data_clean, pk=site["id"])
        self.assertEqual(list(decoded.m2m_data["tags"]), [])
        with self.assertRaisesRegex(ValueError, "tag is missing"):
            self.restore(change)
        OBSERVATIONS.append(
            {
                "case": "missing historical tag",
                "bare_helper_silently_omits": True,
                "prototype_blocks": True,
            }
        )

    def test_07_interface_cascade_and_surviving_device_relationship(self):
        device, _ = self.device()
        interface = self.create(
            "dcim/interfaces/",
            {"device": device["id"], "name": "eth0", "type": "1000base-t"},
        )
        ip = self.create(
            "ipam/ip-addresses/",
            {
                "address": "192.0.2.77/24",
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": interface["id"],
            },
        )
        self.request(
            "PATCH", f"dcim/devices/{device['id']}/", {"primary_ip4": ip["id"]}
        )
        self.request("DELETE", f"dcim/interfaces/{interface['id']}/", expected=204)
        self.assertFalse(IPAddress.objects.filter(pk=ip["id"]).exists())
        self.assertIsNone(Device.objects.get(pk=device["id"]).primary_ip4_id)
        change = self.deletion(Interface, interface["id"])
        siblings = list(
            ObjectChange.objects.filter(request_id=change.request_id).order_by("id")
        )
        self.assertTrue(
            any(
                c.action == "update" and c.changed_object_type.model == "device"
                for c in siblings
            )
        )
        self.restore(change)
        self.restore(self.deletion(IPAddress, ip["id"]))
        self.assertEqual(
            IPAddress.objects.get(pk=ip["id"]).assigned_object_id, interface["id"]
        )
        self.assertIsNone(Device.objects.get(pk=device["id"]).primary_ip4_id)
        self.request(
            "PATCH", f"dcim/devices/{device['id']}/", {"primary_ip4": ip["id"]}
        )
        self.assertEqual(Device.objects.get(pk=device["id"]).primary_ip4_id, ip["id"])
        OBSERVATIONS.append(
            {
                "case": "interface cascade",
                "request_changes": [
                    {"model": c.changed_object_type.model, "action": c.action}
                    for c in siblings
                ],
                "restored_ids": True,
                "surviving_device_requires_separate_correction": True,
            }
        )

    def test_08_primary_id_restore_does_not_regenerate_device_components(self):
        device, dtype = self.device()
        self.create(
            "dcim/interface-templates/",
            {"device_type": dtype["id"], "name": "eth-template", "type": "1000base-t"},
        )
        # Template was added later; the old device deliberately has no interfaces.
        self.assertFalse(Interface.objects.filter(device_id=device["id"]).exists())
        self.request("DELETE", f"dcim/devices/{device['id']}/", expected=204)
        restored = self.restore(self.deletion(Device, device["id"]))
        self.assertFalse(Interface.objects.filter(device=restored).exists())
        recreated = self.create(
            "dcim/devices/",
            {
                "name": self.prefix + "-new",
                "site": restored.site_id,
                "device_type": dtype["id"],
                "role": restored.role_id,
            },
        )
        self.assertEqual(Interface.objects.filter(device_id=recreated["id"]).count(), 1)
        OBSERVATIONS.append(
            {
                "case": "device template side effects",
                "same_id_restore_generates_components": False,
                "fresh_api_create_generates_components": True,
            }
        )

    def test_09_cable_parent_only_restore_is_incomplete(self):
        device, _ = self.device()
        ports = [
            self.create(
                "dcim/interfaces/",
                {"device": device["id"], "name": name, "type": "1000base-t"},
            )
            for name in ("eth0", "eth1")
        ]
        cable = self.create(
            "dcim/cables/",
            {
                "a_terminations": [
                    {"object_type": "dcim.interface", "object_id": ports[0]["id"]}
                ],
                "b_terminations": [
                    {"object_type": "dcim.interface", "object_id": ports[1]["id"]}
                ],
            },
        )
        term_ids = list(
            CableTermination.objects.filter(cable_id=cable["id"]).values_list(
                "pk", flat=True
            )
        )
        self.request("DELETE", f"dcim/cables/{cable['id']}/", expected=204)
        change = self.deletion(Cable, cable["id"])
        self.assertFalse(CableTermination.objects.filter(pk__in=term_ids).exists())
        restored = self.restore(change)
        self.assertEqual(CableTermination.objects.filter(cable=restored).count(), 0)
        children = [self.deletion(CableTermination, pk) for pk in term_ids]
        for child in children:
            self.restore(child)
        self.assertEqual(CableTermination.objects.filter(cable=restored).count(), 2)
        for port in ports:
            self.assertEqual(Interface.objects.get(pk=port["id"]).cable_id, restored.pk)
        OBSERVATIONS.append(
            {
                "case": "cable restore",
                "parent_only_is_incomplete": True,
                "termination_records_available": len(children),
                "separate_child_restore_reconnects_interfaces": True,
            }
        )

    def test_10_tree_restore_recomputes_paths(self):
        parent = self.create(
            "dcim/regions/", {"name": self.prefix, "slug": self.prefix}
        )
        child = self.create(
            "dcim/regions/",
            {
                "name": self.prefix + "-child",
                "slug": self.prefix + "-child",
                "parent": parent["id"],
            },
        )
        before_path = str(Region.objects.get(pk=child["id"]).path)
        self.request("DELETE", f"dcim/regions/{child['id']}/", expected=204)
        restored = self.restore(self.deletion(Region, child["id"]))
        restored.refresh_from_db()
        self.assertEqual(str(restored.path), before_path)
        self.assertEqual(restored.parent_id, parent["id"])
        OBSERVATIONS.append(
            {"case": "hierarchical region", "original_id_and_path_restored": True}
        )

    def test_11_name_collision_blocks_without_overwrite(self):
        site = self.site()
        self.request("DELETE", f"dcim/sites/{site['id']}/", expected=204)
        newer = self.create(
            "dcim/sites/",
            {"name": site["name"], "slug": site["slug"], "description": "new owner"},
        )
        with self.assertRaises(ValidationError):
            self.restore(self.deletion(Site, site["id"]))
        self.assertEqual(Site.objects.get(pk=newer["id"]).description, "new owner")
        self.assertFalse(Site.objects.filter(pk=site["id"]).exists())

    def test_12_graph_recovery_failure_can_roll_back_prior_inserts(self):
        device, _ = self.device()
        interface = self.create(
            "dcim/interfaces/",
            {"device": device["id"], "name": "eth0", "type": "1000base-t"},
        )
        self.request("DELETE", f"dcim/interfaces/{interface['id']}/", expected=204)
        change = self.deletion(Interface, interface["id"])
        with self.assertRaisesRegex(RuntimeError, "injected"), transaction.atomic():
            self.restore(change)
            raise RuntimeError("injected later graph failure")
        self.assertFalse(Interface.objects.filter(pk=interface["id"]).exists())
        self.assertFalse(
            ObjectChange.objects.filter(
                message="Deletion research restore " + str(change.pk)
            ).exists()
        )

    def test_13_stale_etag_rejects_delete(self):
        site = self.site()
        before = self.client.get(f"/api/dcim/sites/{site['id']}/")
        self.request(
            "PATCH", f"dcim/sites/{site['id']}/", {"description": "newer edit"}
        )
        self.request(
            "DELETE",
            f"dcim/sites/{site['id']}/",
            expected=412,
            HTTP_IF_MATCH=before["ETag"],
        )
        self.assertTrue(Site.objects.filter(pk=site["id"]).exists())

    def test_14_custom_field_false_zero_empty_null_survive(self):
        name = self.prefix.replace("-", "_")
        self.create(
            "extras/custom-fields/",
            {"name": name, "type": "json", "object_types": ["dcim.site"]},
        )
        site = self.site()
        data = {"count": 0, "enabled": False, "text": "", "unset": None}
        self.request(
            "PATCH", f"dcim/sites/{site['id']}/", {"custom_fields": {name: data}}
        )
        self.request("DELETE", f"dcim/sites/{site['id']}/", expected=204)
        restored = self.restore(self.deletion(Site, site["id"]))
        self.assertEqual(restored.custom_field_data[name], data)
        OBSERVATIONS.append(
            {"case": "custom field JSON", "false_zero_empty_null_preserved": True}
        )


result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(Probe)
)
print(
    "DELETION_RESEARCH="
    + json.dumps(
        {
            "tests": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "observations": OBSERVATIONS,
        },
        sort_keys=True,
    )
)
if not result.wasSuccessful():
    raise RuntimeError("Deletion research assertions failed")
