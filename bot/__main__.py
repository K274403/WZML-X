from typing import Any, Callable, Coroutine, Final, List, Optional, Tuple

import aiofiles
import asyncio
import logging
import os
import sys
import time
import uuid
from base64 import b64decode
from datetime import datetime
from importlib import import_module, reload
from pytz import timezone
from signal import signal, SIGINT
from sys import executable
from urllib.parse import unquote
from uuid import uuid4

import pyrogram
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import NetworkError
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from .helper.ext_utils.fs_utils import start_cleanup, clean_all, exit_clean_up
from .helper.ext_utils.bot_utils import get_readable_time, cmd_exec, sync_to_async, new_task, set_commands, update_user_ldata, get_stats
from .helper.ext_utils.db_handler import DbManger
from .helper.telegram_helper.bot_commands import BotCommands
from .helper.telegram_helper.message_utils import send_message, edit_message, edit_reply_markup, send_file, delete_message, delete_all_messages
from .helper.telegram_helper.filters import CustomFilters
from .helper.telegram_helper.button_build import ButtonMaker
from .helper.listeners.aria2_listener import start_aria2_listener
from .helper.themes import BotTheme
from .modules import authorize, clone, gd_count, gd_delete, gd_list, cancel_mirror, mirror_leech, status, torrent_search, torrent_select, ytdlp, \
                     rss, shell, eval, users_settings, bot_settings, speedtest, save_msg, images, imdb, anilist, mediainfo, mydramalist, gen_pyro_sess, \
                     gd_clean, broadcast, category_select

LOGGER: Final = logging.getLogger(__name__)

class Bot:
    def __init__(self, token: str, name: str, config_dict: dict, user_data: dict, bot_start_time: float, logger: logging.Logger):
        self.token: str = token
        self.name: str = name
        self.config_dict: dict = config_dict
        self.user_data: dict = user_data
        self.bot_start_time: float = bot_start_time
        self.logger: logging.Logger = logger

    async def start(self):
        self.client: Client = Client(self.token)

        self.client.add_handler(MessageHandler(start, filters=filters.command(BotCommands.StartCommand) & filters.private))
        self.client.add_handler(CallbackQueryHandler(token_callback, filters=filters.regex(r'^pass')))
        self.client.add_handler(MessageHandler(login, filters=filters.command(BotCommands.LoginCommand) & filters.private))
        self.client.add_handler(MessageHandler(log, filters=filters.command(BotCommands.LogCommand) & CustomFilters.sudo))
        self.client.add_handler(MessageHandler(restart, filters=filters.command(BotCommands.RestartCommand) & CustomFilters.sudo))
        self.client.add_handler(MessageHandler(ping, filters=filters.command(BotCommands.PingCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
        self.client.add_handler(MessageHandler(bot_help, filters=filters.command(BotCommands.HelpCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
        self.client.add_handler(MessageHandler(stats, filters=filters.command(BotCommands.StatsCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))

        self.client.add_error_handler(error_handler)

        await self.client.start()

        await gather(start_cleanup(), torrent_search.initiate_search_tools(), restart_notification(), search_images(), set_commands(self.client), log_check())
        await sync_to_async(start_aria2_listener(), wait=False)

        self.logger.info(f"WZML-X Bot [{self.name}] Started!")
        if self.config_dict['USER_BOT_TOKEN']:
            self.logger.info(f"WZ's User Bot [{self.config_dict['USER_BOT_NAME']}] Ready!")
        signal(SIGINT, exit_clean_up)

        await self.client.idle()

    async def stop(self):
        await self.client.stop()

def start_app():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    config_dict: dict = {
        'TOKEN_TIMEOUT': False,
        'LOGIN_PASS': None,
        'BOT_PM': True,
        'IMG_SEARCH': ['anime', 'nature', 'space', 'car', 'girl', 'guy', 'dog', 'cat', 'wolf', 'lion'],
        'IMG_PAGE': 5,
        'TIMEZONE': 'Asia/Kolkata',
        'USER_BOT_TOKEN': None,
        'USER_BOT_NAME': None,
        'LEECH_LOG_ID': None,
        'STATUS_LIMIT': 5,
    }

    user_data: dict = {}

    bot_start_time: float = time.time()

    bot: Bot = Bot(config_dict=config_dict, user_data=user_data, bot_start_time=bot_start_time, logger=LOGGER)

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        asyncio.run(bot.stop())

if __name__ == "__main__":
    start_app()

async def stats(client: Client, message: Message):
    msg, btns = await get_stats(message)
    await send_message(message, msg, btns, photo='IMAGES')

async def start(client: Client, message: Message):
    buttons = ButtonMaker()
    buttons.ubutton(BotTheme('ST_BN1_NAME'), BotTheme('ST_BN1_URL'))
    buttons.ubutton(BotTheme('ST_BN2_NAME'), BotTheme('ST_BN2_URL'))
    reply_markup = buttons.build_menu(2)
    if len(message.command) > 1 and message.command[1] == "wzmlx":
        await delete_message(message)
    elif len(message.command) > 1 and config_dict['TOKEN_TIMEOUT']:
        userid = message.from_user.id
        encrypted_url = message.command[1]
        input_token, pre_uid = (b64decode(encrypted_url.encode()).decode()).split('&&')
        if int(pre_uid) != userid:
            return await send_message(message, BotTheme('OWN_TOKEN_GENERATE'))
        data = user_data.get(userid, {})
        if 'token' not in data or data['token'] != input_token:
            return await send_message(message, BotTheme('USED_TOKEN'))
        elif config_dict['LOGIN_PASS'] is not None and data['token'] == config_dict['LOGIN_PASS']:
            return await send_message(message, BotTheme('LOGGED_PASSWORD'))
        buttons.ibutton(BotTheme('ACTIVATE_BUTTON'), f'pass {input_token}', 'header')
        reply_markup = buttons.build_menu(2)
        msg = BotTheme('TOKEN_MSG', token=input_token, validity=get_readable_time(int(config_dict["TOKEN_TIMEOUT"])))
        return await send_message(message, msg, reply_markup)
    elif await CustomFilters.authorized(client, message):
        start_string = BotTheme('ST_MSG', help_command=f"/{BotCommands.HelpCommand}")
        await send_message(message, start_string, reply_markup, photo='IMAGES')
    elif config_dict['BOT_PM']:
        await send_message(message, BotTheme('ST_BOTPM'), reply_markup, photo='IMAGES')
    else:
        await send_message(message, BotTheme('ST_UNAUTH'), reply_markup, photo='IMAGES')
    await DbManger().update_pm_users(message.from_user.id)

async def token_callback(_, query: pyrogram.types.CallbackQuery):
    user_id = query.from_user.id
    input_token = query.data.split()[1]
    data = user_data.get(user_id, {})
    if 'token' not in data or data['token'] != input_token:
        return await query.answer('Already Used, Generate New One', show_alert=True)
    update_user_ldata(user_id, 'token', str(uuid4()))
    update_user_ldata(user_id, 'time', time())
    await query.answer('Activated Temporary Token!', show_alert=True)
    kb = query.message.reply_markup.inline_keyboard[1:]
    kb.insert(0, [InlineKeyboardButton(BotTheme('ACTIVATED'), callback_data='pass activated')])
    await edit_reply_markup(query.message, InlineKeyboardMarkup(kb))

async def login(_, message: Message):
    if config_dict['LOGIN_PASS'] is None:
        return
    elif len(message.command) > 1:
        user_id = message.from_user.id
        input_pass = message.command[1]
        if user_data.get(user_id, {}).get('token', '') == config_dict['LOGIN_PASS']:
            return await send_message(message, BotTheme('LOGGED_IN'))
        if input_pass != config_dict['LOGIN_PASS']:
            return await send_message(message, BotTheme('INVALID_PASS'))
        update_user_ldata(user_id, 'token', config_dict['LOGIN_PASS'])
        return await send_message(message, BotTheme('PASS_LOGGED'))
    else:
        await send_message(message, BotTheme('LOGIN_USED'))

async def restart(client: Client, message: Message):
    restart_message = await send_message(message, BotTheme('RESTARTING'))
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await delete_all_messages()
    for interval in [QbInterval, Interval]:
        if interval:
            interval[0].cancel()
    await sync_to_async(clean_all)
    proc1 = await create_subprocess_exec('pkill', '-9', '-f', 'gunicorn|aria2c|qbittorrent-nox|ffmpeg|rclone')
    proc2 = await create_subprocess_exec('python3', 'update.py')
    await gather(proc1.wait(), proc2.wait())
    async with aiofiles.open(".restartmsg", "w") as f:
        await f.write(f"{restart_message.chat.id}\n{restart_message.id}\n")
    osexecl(executable, executable, "-m", "bot")

async def ping(_, message: Message):
    start_time = monotonic()
    reply = await send_message(message, BotTheme('PING'))
    end_time = monotonic()
    await edit_message(reply, BotTheme('PING_VALUE', value=int((end_time - start_time) * 1000)))

async def log(_, message: Message):
    buttons = ButtonMaker()
    buttons.ibutton(BotTheme('LOG_DISPLAY_BT'), f'wzmlx {message.from_user.id} logdisplay')
    buttons.ibutton(BotTheme('WEB_PASTE_BT'), f'wzmlx {message.from_user.id} webpaste')
    await send_file(message, 'log.txt', buttons=buttons.build_menu(1))

async def search_images():
    if not (query_list := config_dict['IMG_SEARCH']):
        return
    try:
        total_pages = config_dict['IMG_PAGE']
        base_url = "https://www.wallpaperflare.com/search"
        for query in query_list:
            query = query.strip().replace(" ", "+")
            for page in range(1, total_pages + 1):
                url = f"{base_url}?wallpaper={query}&width=1280&height=720&page={page}"
                r = rget(url)
                soup = BeautifulSoup(r.text, "html.parser")
                images = soup.select('img[data-src^="https://c4.wallpaperflare.com/wallpaper"]')
                if len(images) == 0:
                    LOGGER.info("Maybe Site is Blocked on your Server, Add Images Manually !!")
                for img in images:
                    img_url = img['data-src']
                    if img_url not in config_dict['IMAGES']:
                        config_dict['IMAGES'].append(img_url)
        if len(config_dict['IMAGES']) != 0:
            config_dict['STATUS_LIMIT'] = 2
        if DATABASE_URL:
            await DbManger().update_config({'IMAGES': config_dict['IMAGES'], 'STATUS_LIMIT': config_dict['STATUS_LIMIT']})
    except Exception as e:
        LOGGER.error(f"An error occurred: {e}")

async def bot_help(client: Client, message: Message):
    buttons = ButtonMaker()
    user_id = message.from_user.id
    buttons.ibutton(BotTheme('BASIC_BT'), f'wzmlx {user_id} guide basic')
    buttons.ibutton(BotTheme('USER_BT'), f'wzmlx {user_id} guide users')
    buttons.ibutton(BotTheme('MICS_BT'), f'wzmlx {user_id} guide miscs')
    buttons.ibutton(BotTheme('O_S_BT'), f'wzmlx {user_id} guide admin')
    buttons.ibutton(BotTheme('CLOSE_BT'), f'wzmlx {user_id} close')
    await send_message(message, BotTheme('HELP_HEADER'), buttons.build_menu(2))

async def restart_notification():
    now=datetime.now(timezone(config_dict['TIMEZONE']))
    if await aiopath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
    else:
        chat_id, msg_id = 0, 0

    async def send_incompelete_task_message(cid: int, msg: str):
        try:
            if msg.startswith("⌬ <b><i>Restarted Successfully!</i></b>"):
                await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=msg, disable_web_page_preview=True)
                await aioremove(".restartmsg")
            else:
                await bot.send_message(chat_id=cid, text=msg, disable_web_page_preview=True, disable_notification=True)
        except Exception as e:
            LOGGER.error(e)

    if INCOMPLETE_TASK_NOTIFIER and DATABASE_URL:
        if notifier_dict := await DbManger().get_incomplete_tasks():
            for cid, data in notifier_dict.items():
                msg = BotTheme('RESTART_SUCCESS', time=now.strftime('%I:%M:%S %p'), date=now.strftime('%d/%m/%y'), timz=config_dict['TIMEZONE'], version=get_version()) if cid == chat_id else BotTheme('RESTARTED')
                msg += "\n\n⌬ <b><i>Incomplete Tasks!</i></b>"
                for tag, links in data.items():
                    msg += f"\n➲ <b>User:</b> {tag}\n┖ <b>Tasks:</b>"
                    for index, link in enumerate(links, start=1):
                        msg_link, source = next(iter(link.items()))
                        msg += f" {index}. <a href='{source}'>S</a> ->  <a href='{msg_link}'>L</a> |"
                        if len(msg.encode()) > 4000:
                            await send_incompelete_task_message(cid, msg)
                            msg = ''
                if msg:
                    await send_incompelete_task_message(cid, msg)

    if await aiopath.isfile(".restartmsg"):
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=BotTheme('RESTART_SUCCESS', time=now.strftime('%I:%M:%S %p'), date=now.strftime('%d/%m/%y'), timz=config_dict['TIMEZONE'], version=get_version()))
        except Exception as e:
            LOGGER.error(e)
        await aioremove(".restartmsg")

async def log_check():
    if config_dict['LEECH_LOG_ID']:
        for chat_id in config_dict['LEECH_LOG_ID'].split():
            chat_id, *topic_id = chat_id.split(":")
            try:
                chat = await bot.get_chat(int(chat_id))
            except Exception:
                LOGGER.error(f"Not Connected Chat ID : {chat_id}, Make sure the Bot is Added!")
                continue
            if chat.type == ChatType.CHANNEL:
                if not (await chat.get_member(bot.me.id)).privileges.can_post_messages:
                    LOGGER.error(f"Not Connected Chat ID : {chat_id}, Make the Bot is Admin in Channel to Connect!")
                    continue
                if user and not (await chat.get_member(user.me.id)).privileges.can_post_messages:
                    LOGGER.error(f"Not Connected Chat ID : {chat
