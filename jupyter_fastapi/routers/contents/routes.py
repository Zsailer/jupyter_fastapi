from fastapi import APIRouter, HTTPException

from jupyter_server.utils import maybe_future
from .types import *

router = APIRouter()


@router.get(
    '/api/contents/{path}', 
    response_model=ContentsModel
)
async def get_content(
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


@router.patch(
    '/api/contents/{path}',
    response_model=ContentsModel
)
async def rename_content(path: str, model: RenameModel):
    """PATCH renames a file or directory without re-uploading content."""
    cm = router.app.contents_manager
    if model is None:
        raise HTTPException(
            status_code=400, 
            detail='JSON body missing'
        )
    model = await maybe_future(cm.update(model.dict(), path))
    return ContentsModel(**model)


@router.post(
    '/api/contents/{path}', 
    status_code=201,
    response_model=ContentsModel
)
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


@router.put(
    '/api/contents/{path}',
    response_model=ContentsModel
)
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
def delete_content(path: str):
    cm = router.app.contents_manager
    cm.delete(path)