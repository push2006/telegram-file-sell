"""Mocked chat-handler tests. No Telegram or MongoDB connection is used."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Filter:
    def __and__(self, other): return self
    def __or__(self, other): return self
    def __invert__(self): return self
    def __call__(self, *args, **kwargs): return self
    def __getattr__(self, name): return self


class Client:
    @staticmethod
    def on_message(*args, **kwargs): return lambda fn: fn
    on_callback_query = on_message


def load_ui():
    hydro = ModuleType('hydrogram'); hydro.Client = Client; hydro.filters = Filter()
    enums = ModuleType('hydrogram.enums'); enums.ParseMode = NS(DISABLED=None)
    types = ModuleType('hydrogram.types'); types.InlineKeyboardButton = lambda text, **kw: NS(text=text, **kw); types.InlineKeyboardMarkup = lambda rows: rows
    helper = ModuleType('helper'); plugins = ModuleType('plugins'); plugins.business = NS(approved=mock.AsyncMock(return_value=False))
    forms = load('mock_easy_forms', ROOT/'helper/easy_forms.py')
    with mock.patch.dict(sys.modules, {'hydrogram':hydro,'hydrogram.enums':enums,'hydrogram.types':types,'helper':helper,'helper.easy_forms':forms,'plugins':plugins}):
        return load('mock_easy_ui',ROOT/'plugins/easy_ui.py')


class Navigation(IsolatedAsyncioTestCase):
    def setUp(self):
        self.ui = load_ui()
        self.state = {'_id':123,'action':'addproduct','values':[], 'labels':[], 'token':'first','prompt_id':42}
        self.collection = NS(find_one=mock.AsyncMock(return_value=self.state), delete_one=mock.AsyncMock(return_value=NS(deleted_count=1)))
        self.client = NS(owner=999,mongodb=NS(db=NS(easy_ui_sessions=self.collection),is_banned=mock.AsyncMock(return_value=False)))
        self.ui.send = mock.AsyncMock()
        self.ui.change = mock.AsyncMock()
        self.ui.execute = mock.AsyncMock()
        self.message = NS(from_user=NS(id=123),text='My course',reply_to_message=None,stop_propagation=mock.Mock())

    async def test_plain_chat_input(self):
        await self.ui.easy_reply(self.client,self.message)
        self.ui.change.assert_awaited_once_with(self.client,123,self.state,['My course'],['My course'])
        self.message.stop_propagation.assert_called_once()

    async def test_old_reply_does_not_change_form(self):
        self.message.reply_to_message=NS(id=41)
        await self.ui.easy_reply(self.client,self.message)
        self.ui.change.assert_not_awaited()
        self.message.stop_propagation.assert_called_once()

    async def test_invalid_price_keeps_step(self):
        self.state['values']=['Course']; self.state['labels']=['Course']; self.message.text='0'
        await self.ui.easy_reply(self.client,self.message)
        self.ui.change.assert_not_awaited()
        self.ui.send.assert_awaited()

    async def test_search_without_confirmation(self):
        self.state['action']='search'; self.message.text='Science'
        await self.ui.easy_reply(self.client,self.message)
        self.ui.execute.assert_awaited_once_with(self.client,self.message,self.message.from_user,'search','Science')

    async def test_owner_action_blocked(self):
        self.assertFalse(await self.ui.allowed(self.client,123,'reviewapplication'))
        self.assertFalse(await self.ui.allowed(self.client,123,'linkchannel'))
        self.assertTrue(await self.ui.allowed(self.client,999,'reviewapplication'))

    async def test_duplicate_confirmation_not_executed(self):
        self.state.update(action='ticket',values=['Help'],paused=False)
        q=NS(from_user=NS(id=123),message=NS(chat=NS(id=123)),data='easy:confirm:first',answer=mock.AsyncMock())
        self.collection.delete_one.return_value=NS(deleted_count=0)
        await self.ui.easy_callback(self.client,q)
        self.ui.execute.assert_not_awaited()
