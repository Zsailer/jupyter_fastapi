import pytest
import hypothesis
import hypothesis_jsonschema
from jupyter_fastapi.app import JupyterFastAPI
from starlette.testclient import TestClient

from jupyter_fastapi.routers.contents.types import RenameModel

@pytest.fixture
def get_client(tmp_path):
    """A fixture that creates a Server Application (with kwargs) and 
    returns a starlette TestClient for that application.
    """
    def configured_client(**app_kwargs):
        serverapp = JupyterFastAPI(root_dir=str(tmp_path), **app_kwargs)
        serverapp.initialize([])
        client = TestClient(serverapp.app)
        return client
    return configured_client


def schema(dataclass):



schema = lambda dataclass: hypothesis_jsonschema.from_schema(dataclass.schema())


def test_get(get_client, tmp_path):
    client = get_client()
    tmp_file = tmp_path / 'test.txt'
    tmp_file.write_text('test')

    response = client.get("/api/contents/test.txt")
    assert response.status_code == 200
    #assert response.json()


@hypothesis.given(body=schema(RenameModel))
def test_rename(get_client, tmp_path, body):
    client = get_client()
    tmp_file = tmp_path / 'test.txt'
    tmp_file.write_text('test')
    
    response = client.patch(
        '/api/contents/test.txt', 
        json=body
    )


    new_name = body['path']
    assert response.json()['path'] == new_name