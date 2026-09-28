"""Selected adapter experiment: mutations through patched SDK MCP; reads via REST."""
from api import API
from compare import unpack
from mcp_client import candidate

class SDKBridge(API):
    def __init__(self):
        super().__init__();self.mcp=candidate('sdk-patched')
    def request(self,method,path,data=None,headers=None):
        if method not in ('PATCH','POST'):return super().request(method,path,data,headers)
        parts=path.strip('/').split('/')
        args={'group':parts[0],'resource':parts[1],'payload':data}
        if method=='PATCH':args['id']=int(parts[2])
        if headers:args['header']=[f'{k}: {v}' for k,v in headers.items()]
        response=self.mcp.tool('patch' if method=='PATCH' else 'create',**args)
        result=unpack(response)
        if not isinstance(result,dict) or 'status' not in result:raise RuntimeError('MCP did not return an HTTP receipt: '+str(result))
        result['headers']={k.lower():v for k,v in result.get('headers',{}).items()}
        return result
