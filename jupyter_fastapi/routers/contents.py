from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

from jupyter_server.utils import maybe_future
from jupyter_server.services.contents.handlers import validate_model


router = APIRouter()


class Model(BaseModel):
    name: str
    path: str
    type: str
    writable: bool
    created: datetime
    last_modified: datetime
    mimetype: str = None
    content: dict = None
    format: str = None


@router.get('/api/contents/{path}')
async def get_model(
    path: str, 
    type: str = None, 
    format: str = None, 
    content: str = '1'
    ):
    """Return a model for a file or directory.

    A directory model contains a list of models (without content)
    of the files and directories it contains.
    """
    content = int(content)
    model = await maybe_future(router.app.contents_manager.get(
        path=path, type=type, format=format, content=content,
    ))
    model = Model(**model)
    return model


# @router.patch('/api/contents/{path}')
# async def rename_file(path: str, model: Model):
#     """PATCH renames a file or directory without re-uploading content."""
#     cm = router.app.contents_manager
#     if model is None:
#         raise web.HTTPError(400, u'JSON body missing')
#     model = await maybe_future(cm.update(model.dict(), path))
#     model = Model(**model)
#     return model
