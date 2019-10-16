from datetime import datetime
from types import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jupyter_server.utils import maybe_future

from starlette.websockets import WebSocket
from starlette.responses import Response

router = APIRouter()


class Kernel(BaseModel):
    id: str
    name: str
    last_activity: datetime
    execution_state: str
    connections: dict


@router.get('/api/kernels', response_model=List[Kernel])
async def list_kernels():
    self = router.app
    km = self.kernel_manager
    kernels = await km.list_kernels()
    # Validate model
    kernels = [Kernel(**k) for k in kernels]
    return kernels


class NewKernelModel(BaseModel):
    name: str

@router.post(
    '/api/kernels', 
    status_code=201,
    response_model=Kernel
)
async def start_kernel(model: NewKernelModel, response: Response):
    self = router.app
    km = self.kernel_manager
    if model is None:
        model = {
            'name': km.default_kernel_name
        }
    else:
        model.setdefault('name', km.default_kernel_name)
    kernel_id = await km.start_kernel(kernel_name=model['name'])
    kernel = await km.kernel_model(kernel_id)
    location = url_path_join(self.base_url, 'api', 'kernels', url_escape(kernel_id))
    repsonse.headers['Location'] = location
    # Validate model!
    return Kernel(**kernel)


@router.get(
    '/api/kernels/{kernel_id}'
)
async def get_kernel_data(kernel_id: str):
    self = router.app
    km = self.kernel_manager
    model = km.kernel_model(kernel_id)
    return Kernel(**model)


@router.delete(
    '/api/kernels/{kernel_id}',
    status_code=204,
)
async def delete_kernel(kernel_id: str):
    self = router.app
    km = self.kernel_manager
    await km.shutdown_kernel(kernel_id)


@router.post(
    '/api/kernels/{kernel_id}/interrupt',
    status_code=204,
)
async def interrupt_kernel(kernel_id: str):
    self = router.app
    km = self.kernel_manager    
    km.interrupt_kernel(kernel_id)


@router.post(
    '/api/kernels/{kernel_id}/restart',
    status_code=204,
    response_model=Kernel
)
async def restart_kernel(kernel_id: str):
    self = router.app
    km = self.kernel_manager    

    try:
        await km.restart_kernel(kernel_id)
    except Exception as e:
        self.log.error("Exception restarting kernel", exc_info=True)
        raise e
    else:
        model = await km.kernel_model(kernel_id)
        return Kernel(**model)
        

# @router.websocket('/api/kernels/{kernel_id}/channels')
# async def websocket_endpoint(websocket: Websocket):
#     await websocket.accept()
#     while True:
#         data = await websocket.receive_json()
#         await websocket.send_json(data)