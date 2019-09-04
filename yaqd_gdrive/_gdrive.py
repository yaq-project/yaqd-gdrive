import asyncio
import functools
import time
import webbrowser

import aiohttp
import aiohttp.web
import yaqd_core


def refresh_oauth(func):
    @functools.wraps(func)
    async def inner(self, *args, **kwargs):
        res = await func(self, *args, **kwargs)
        if res.status == 200:
            return res
        #self._access_token = None
        try:
            await self._use_refresh_token()
        except:
            await self._authorize()

        return await func(self, *args, **kwargs)
    return inner


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
        self._http_session = aiohttp.ClientSession()
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
        self._loop.create_task(self._stock_ids())
        self._loop.create_task(self._upload())

    @property
    def _auth_header(self):
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _authorize(self):
        code = asyncio.Future()
        port=9004
        url = f"{self._authorization_url}?scope={'%20'.join(self._scopes)}&response_type=code&redirect_uri=http://127.0.0.1:{port}&client_id={self._client_id}"
        app = aiohttp.web.Application()

        async def complete_auth(request):
            nonlocal code, url
            if "code" in request.query:
                code.set_result(request.query["code"])
                return aiohttp.web.Response(text="Authorization complete")
            else:
                return aiohttp.web.Response(
                    text=f"Authorization failed\n{request.query.get('error', '')}\n{url}"
                )

        app.add_routes([aiohttp.web.get("/", complete_auth)])

        webbrowser.open(url)

        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "localhost", port)
        await site.start()
        code = await code
        await runner.cleanup()
        await self._obtain_token(code)
        self._busy.set()

    async def _obtain_token(self, code):
        async with self._http_session.post(
            self._token_url,
            json={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": "http://127.0.0.1:9004",
                "grant_type": "authorization_code",
            },
        ) as res:
            print(await res.text())
            res.raise_for_status()
            json = await res.json()
            self._access_token = json["access_token"]
            self._refresh_token = json["refresh_token"]
        # TODO: Auto refresh using "expires_in"?

    async def _use_refresh_token(self):
        print("Refreshing token")
        async with self._http_session.post(
            self._token_url,
            json={
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
        ) as res:
            res.raise_for_status()
            self._access_token = (await res.json())["access_token"]
            return res
        # TODO: Auto refresh using "expires_in"?

    @refresh_oauth
    async def _create_file(self, name, parent, file_=None, *, id_=None, mime_type=None):
        # TODO: investigate using resumable uploads instead of multipart
        # May be more reliable
        with aiohttp.MultipartWriter('related') as mpwriter:
            mpwriter.append_json({"name": name, "parents":[parent], "id":id_, "mimeType":mime_type})
            if file_ is not None:
                mpwriter.append(file_)
            async with self._http_session.post(
                self._create_file_url,
                headers=self._auth_header,
                params={"uploadType":"multipart"},
                data=mpwriter,
            ) as res:
                print(res)
                print(await res.json())
                return res

    async def _create_folder(self, name, parent, *, id_=None):
        await self._create_file(name, parent, id_=id_, mime_type="application/vnd.google-apps.folder")

    @refresh_oauth
    async def _update_file(self, file_, id_):
        with aiohttp.MultipartWriter('related') as mpwriter:
            mpwriter.append(file_)
            async with self._http_session.patch(
                f"{self._update_file_url}/{id_}",
                headers=self._auth_header,
                params={"uploadType":"multipart"},
                data=mpwriter,
            ) as res:
                return res

    @refresh_oauth
    async def _generate_ids(self, count=128):
        async with self._http_session.get(
                self._generate_ids_url,
                headers=self._auth_header,
                params={"count":count, "space":"drive"}
        ) as res:
            if res.status == 200:
                ids = (await res.json())["ids"]
                self._free_ids += ids
            return res

    def get_state(self):
        return {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "upload_queue": self._upload_queue,
                "id_mapping": self._id_mapping,
                }

    def _load_state(self, state):
        self._access_token = state.get("access_token")
        self._refresh_token = state.get("refresh_token")
        self._upload_queue = state.get("upload_queue", {})
        self._id_mapping = state.get("id_mapping", {})

    async def update_state(self):
        while True:
            if self._busy.is_set():
                self._not_busy.set()
            await self._busy.wait()

    async def _stock_ids(self):
        while True:
            if len(self._free_ids) < 32:
                await self._generate_ids()
            await self._not_busy.wait()

    async def _upload(self):
        while True:
            while self._upload_queue:
                pass
            await asyncio.sleep(1)

if __name__ == "__main__":
    GDriveDaemon.defaults.update({"client_id":"943700362860-7fmktmg2rjrblt4v2qh86141l6vg7qju.apps.googleusercontent.com", "client_secret":"pKIjNEasosRswlt4xWOxQCpD", "root_folder_id":"1oZOabPMoTO2XPE5mWOC_9XOR9PsUgepC"})
    gdrive = GDriveDaemon("test",GDriveDaemon.defaults, "")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(gdrive._generate_ids())
    print(gdrive._free_ids)

