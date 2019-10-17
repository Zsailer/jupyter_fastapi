from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jupyter_server.utils import maybe_future, url_path_join, url_escape

from starlette.responses import Response

from .zmqstream import ZMQChannels
from starlette.websockets import WebSocket

router = APIRouter()


class Kernel(BaseModel):
    id: str
    name: str
    last_activity: datetime
    execution_state: str
    connections: int


@router.get('/api/kernels', response_model=List[Kernel])
async def list_kernels():
    self = router.app
    km = self.kernel_manager
    kernels = await maybe_future(km.list_kernels())
    # Validate model
    kernels = [Kernel(**k) for k in kernels]
    return kernels


class NewKernelModel(BaseModel):
    name: str = None


@router.post(
    '/api/kernels', 
    status_code=201,
    response_model=Kernel
)
async def create_kernel(response: Response, model: NewKernelModel = None):
    self = router.app
    km = self.kernel_manager
    if model is None:
        kernel_name = km.default_kernel_name
    elif model.name is None:
        kernel_name = km.default_kernel_name
    else:
        kernel_name = model.name
    kernel_id = await maybe_future(km.start_kernel(kernel_name=kernel_name))
    kernel = await maybe_future(km.kernel_model(kernel_id))
    location = url_path_join(self.base_url, 'api', 'kernels', url_escape(kernel_id))
    response.headers['Location'] = location
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
    await maybe_future(km.shutdown_kernel(kernel_id))


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
        await maybe_future(km.restart_kernel(kernel_id))
    except Exception as e:
        self.log.error("Exception restarting kernel", exc_info=True)
        raise e
    else:
        model = await maybe_future(km.kernel_model(kernel_id))
        return Kernel(**model)



class ZMQWebsocket(WebSocket, ZMQChannels):

    async def accept(self, kernel_id):
        await super(ZMQWebsocket, self).accept()
        self.open(kernel_id)

    async def receive_json(self, msg):
        data = await super(ZMQWebsocket, self).receive_json(msg)
        self.on_message(data)

    async def write_message(self, json_msg):
        await super(ZMQWebsocket, self).send_json(json_msg)


@router.websocket('/api/kernels/{kernel_id}/channels')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_json()
