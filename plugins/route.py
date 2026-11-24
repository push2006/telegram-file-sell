# Modifications copyright push2006. Original notices and LICENSE retained.
from aiohttp import web
routes = web.RouteTableDef()
@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"service":"push2006", "http":"ok"})
