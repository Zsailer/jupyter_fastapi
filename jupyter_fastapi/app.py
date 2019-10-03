import importlib
from fastapi import FastAPI
from jupyter_server.serverapp import ServerApp

import uvicorn


class JupyterFastAPI(ServerApp):

    routers = [
        'contents'
    ]

    def init_webapp(self):
        self.app = FastAPI(
            title="Jupyter Server",
            description="Jupyter Server implementation powered by FastAPI."
        )
        # Add routes.
        for router in self.routers:
            mod = importlib.import_module('jupyter_fastapi.routers.' + router)
            mod.router.app = self
            self.app.include_router(mod.router)
        
    def initialize(self, argv=None):
        super(ServerApp, self).initialize(argv)
        self.init_configurables()
        self.init_webapp()

    def start(self):
        super(ServerApp, self).start()
        # Make application available from globals
        uvicorn.run(self.app, host=self.ip, port=self.port)


main = JupyterFastAPI.launch_instance


