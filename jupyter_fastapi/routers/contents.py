from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jupyter_server.utils import maybe_future
from jupyter_server.services.contents.handlers import validate_model


router = APIRouter()


class ContentsModel(BaseModel):
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
    cm = router.app.contents_manager
    content = int(content)
    model = await maybe_future(cm.get(
        path=path, type=type, format=format, content=content,
    ))
    return ContentsModel(**model)


class RenameModel(BaseModel):
    path: str


@router.patch('/api/contents/{path}')
async def rename_file(path: str, model: RenameModel):
    """PATCH renames a file or directory without re-uploading content."""
    cm = router.app.contents_manager
    if model is None:
        raise HTTPException(
            status_code=400, 
            detail='JSON body missing'
        )
    model = await maybe_future(cm.update(model.dict(), path))
    return ContentsModel(**model)


class CreateModel(BaseModel):
    copy_from: str = None
    ext: str
    type: str


@router.post('/api/contents/{path}', status_code=201)
async def create_content(path: str, model: CreateModel = None):
    """Create a new file in the specified path.

    POST creates new files. The server always decides on the name.

    POST /api/contents/path
        New untitled, empty file or directory.
    POST /api/contents/path
        with body {"copy_from" : "/path/to/OtherNotebook.ipynb"}
        New copy of OtherNotebook in path
    """
    cm = router.app.contents_manager

    file_exists = await maybe_future(cm.file_exists(path))
    if file_exists:
        raise HTTPException(
            status_code=400, 
            detail="Cannot POST to files, use PUT instead."
        )

    dir_exists = await maybe_future(cm.dir_exists(path))
    if not dir_exists:
        raise HTTPException(
            status_code=404, 
            detail="No such directory: %s" % path
        )

    if model is not None:
        if model.copy_from:
            model = await maybe_future(cm.copy(copy_from, copy_to))
        else:
            model = await maybe_future(cm.new_untitled(
                path=path, type=model.type, ext=model.ext))
    else:
        model = await maybe_future(cm.new_untitled(
                path=path, type='', ext=''))

    return ContentsModel(**model)


class SaveModel(BaseModel):
    name: str
    path: str
    type: str
    format: str
    content: str


@router.put('/api/contents/{path}')
async def save_content(path: str, model: SaveModel = None):
    cm = router.app.contents_manager
    if model:
        if model.copy_from:
            raise HTTPException(
                status_code=400, 
                detail="Cannot copy with PUT, only POST"
            )
        exists = await maybe_future(cm.file_exists(path))
        if exists:
            model = await maybe_future(cm.save(model, path))
        else:
            model = await maybe_future(cm.new(model, path))
    else:
        model = await maybe_future(cm.new_untitled(
            path=path, type=model.type, ext=model.ext))
    return ContentsModel(**model)


@router.delete('/api/contents/{path}', status_code=204)
def delete_file(path: str):
    cm = router.app.contents_manager
    cm.delete(path)