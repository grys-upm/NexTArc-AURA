"""Registry Service gRPC handler for managing user inference script metadata records.

Saves, lists, retrieves, and deletes custom scripts in the database.
"""
import grpc
from sqlalchemy.ext.asyncio import async_sessionmaker
from shared.proto_gen import script_pb2, script_pb2_grpc
from app.repositories.scripts import ScriptRepository

def _to_proto(sc) -> script_pb2.ScriptResponse:
    """Formats an ORM Script record to its corresponding Protobuf message type.

    Args:
        sc: The ORM Script entity instance.

    Returns:
        The populated ScriptResponse Protobuf object.
    """
    return script_pb2.ScriptResponse(
        id=sc.id, name=sc.name, description=sc.description or "",
        language=sc.language, script_key=sc.script_key,
        script_sha256=sc.script_sha256, created_at=sc.created_at.isoformat(),
    )

class ScriptServiceHandler(script_pb2_grpc.ScriptServiceServicer):
    """gRPC Service Servicer handling user script lifecycle actions."""

    def __init__(self, sf: async_sessionmaker):
        """Initializes the Script Service Handler.

        Args:
            sf: Database async session maker class.
        """
        self._sf = sf

    async def UploadScript(self, req: script_pb2.UploadScriptRequest, ctx: grpc.aio.ServicerContext) -> script_pb2.ScriptResponse:
        """Registers a new inference script entry in the database.

        Args:
            req: Script upload parameters request.
            ctx: gRPC connection context.

        Returns:
            The created ScriptResponse.
        """
        async with self._sf() as s:
            sc = await ScriptRepository(s).create(req.name, req.description or None,
                                                   req.language,
                                                   req.script_key, req.script_sha256)
            return _to_proto(sc)

    async def GetScript(self, req: script_pb2.GetScriptRequest, ctx: grpc.aio.ServicerContext) -> script_pb2.ScriptResponse:
        """Retrieves metadata of a single script by its ID.

        Args:
            req: Script request ID parameters.
            ctx: gRPC connection context.

        Returns:
            ScriptResponse details.
        """
        async with self._sf() as s:
            sc = await ScriptRepository(s).get(req.id)
            if not sc:
                ctx.abort(grpc.StatusCode.NOT_FOUND, "Script not found")
                return
            return _to_proto(sc)

    async def ListScripts(self, req: script_pb2.ListScriptsRequest, ctx: grpc.aio.ServicerContext) -> script_pb2.ListScriptsResponse:
        """Lists all registered inference scripts.

        Args:
            req: Empty query request message.
            ctx: gRPC connection context.

        Returns:
            ListScriptsResponse containing scripts.
        """
        async with self._sf() as s:
            scripts = await ScriptRepository(s).list_all()
            return script_pb2.ListScriptsResponse(scripts=[_to_proto(sc) for sc in scripts])

    async def DeleteScript(self, req: script_pb2.DeleteScriptRequest, ctx: grpc.aio.ServicerContext) -> script_pb2.DeleteScriptResponse:
        """Removes a script record from the database registry.

        Args:
            req: Target script ID.
            ctx: gRPC connection context.

        Returns:
            DeleteScriptResponse indicator.
        """
        async with self._sf() as s:
            ok = await ScriptRepository(s).delete(req.id)
            if not ok:
                ctx.abort(grpc.StatusCode.NOT_FOUND, "Script not found")
                return
            return script_pb2.DeleteScriptResponse(success=True)
