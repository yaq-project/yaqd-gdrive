import asyncio
import time

import httpx
import yaqd_core


def refresh_oauth(func):
    @functools.wraps(func)
    async def inner(self, *args, **kwargs):
        res = await func(self, *args, **kwargs)
        if res.status_code == 200:
            return res
        self._authorized = False
        try:
            await self._refresh_token()
        except httpx.HTTPError:
            await self._authorize()

        return await func(self, *args, **kwargs)


class GDriveDaemon(yaqd_core.BaseDaemon):
    _kind = "gdrive"
    defaults = {
        "scopes": ["https://www.googleapis.com/auth/drive.file"],
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://www.googleapis.com/oauth2/v4/token",
        "create_file_url": "https://www.googleapis.com/upload/drive/v3/files",
        "generate_ids_url": "https://www.googleapis.com/drive/v3/files/generateIds",
        "update_file_url": "https://www.googleapis.com/upload/drive/v3/files/",  # Needs fileId
    }

    def __init__(self, name, config, config_filepath):
        self._http_client = httpx.AsyncClient()
        self._upload_queue = {}
        self._id_mapping = {}
        self._free_ids = []
        self._access_token = None
        self._refresh_token = None
        super().__init__(name, config, config_filepath)
        self._client_secret = config["client_secret"]
        self._client_id = config["client_id"]
        self._root_folder_id = config["root_folder_id"]
        self._scopes = config["scopes"]
        self._authorization_url = config["authorization_url"]
        self._token_url = config["token_url"]
        self._create_file_url = config["create_file_url"]
        self._generate_ids_url = config["generate_ids_url"]
        self._update_file_url = config["update_file_url"]

    async def _authorize(self):

        await self._obtain_token(code)

    async def _obtain_token(self, code):
        res = await self._http_client.post(
            self._token_url,
            params={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": "https://127.0.0.1:9004",
                "grant_type": "authorization_code",
            },
        )
        res.raise_for_status()
        json = res.json()
        self._access_token = json["access_token"]
        self._refresh_token = json["refresh_token"]
        # TODO: Auto refresh using "expires_in"?

    async def _refresh_token(self):
        res = await self._http_client.post(
            self._token_url,
            params={
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
        )
        res.raise_for_status()
        self._access_token = res.json()["access_token"]
        # TODO: Auto refresh using "expires_in"?

    @refresh_oauth
    async def _create_file(self, id_=None):
        pass

    @refresh_oauth
    async def _create_folder(self, id_=None):
        pass

    @refresh_oauth
    async def _update_file(self, id_):
        pass

    @refresh_oauth
    async def _generate_ids(self, count=128):
        pass
