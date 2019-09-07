# -*- coding: utf-8 -*-
from urllib.parse import quote_plus
import gettext
import os
import random
import string
import sqlite3

from jinja2 import Environment, PackageLoader, select_autoescape
from simplebot import Plugin
import deltachat as dc


PUBLIC = 1
PRIVATE = 0
DELTA_URL = 'http://delta.chat/group/'


class GroupMaster(Plugin):

    name = 'GroupMaster'
    version = '0.2.0'

    @classmethod
    def activate(cls, bot):
        super().activate(bot)

        cls.env = Environment(
            loader=PackageLoader(__name__, 'templates'),
            autoescape=select_autoescape(['html', 'xml'])
        )

        cls.db = DBManager(os.path.join(
            cls.bot.get_dir(__name__), 'groupmaster.db'))

        localedir = os.path.join(os.path.dirname(__file__), 'locale')
        lang = gettext.translation('simplebot_groupmaster', localedir=localedir,
                                   languages=[bot.locale], fallback=True)
        lang.install()

        cls.description = _(
            'Extends the capabilities of DeltaChat groups.')
        cls.commands = [
            ('/group/id', [], _('Shows the id of the group where it is sent.'), cls.id_cmd),
            ('/group/list', [], _('Will show the list of public groups.'), cls.list_cmd),
            ('/group/join',
             ['<id>'], _('Will join you to the public group with the given id.'), cls.join_cmd),
            ('/group/leave', ['[id]'], _(
                'Will remove you from the group with the given id or the group where it is sent if no id was passed.'), cls.leave_cmd),
            ('/group/public', [],
             _('Send it in a group to make it public.'), cls.public_cmd),
            ('/group/private', [],
             _('Send it in a group to make it private.'), cls.private_cmd),
            ('/group/topic', ['[topic]'],
             _('Show the current topic or replace it.'), cls.topic_cmd),
            ('/group/add', ['<id>', '<addrs>'], _(
                'Will add a comma-separated list of addresses to the group with the given id.'), cls.add_cmd),
            ('/group/remove', ['<id>', '<addr>'], _(
                'Will remove the member with the given address from the group with the give id.'), cls.remove_cmd),
            ('/group/msg', ['<id>', '<msg>'], _(
                'Will send the given message to the group with the given id.'), cls.msg_cmd)]
        cls.bot.add_commands(cls.commands)

        cls.LIST_BTN = _('Groups List')
        cls.JOIN_BTN = _('Join')
        cls.LEAVE_BTN = _('Leave')

    @classmethod
    def deactivate(cls):
        super().deactivate()
        cls.db.close()

    @classmethod
    def get_info(cls, gid):
        info = cls.db.execute(
            'SELECT pid,topic,status FROM groups WHERE id=?', (gid,), 'one')
        if info is None:
            pid = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits)
                          for i in range(10))
            info = (pid, '', PRIVATE)
            cls.db.insert((gid, *info))
        return info

    @classmethod
    def get_groups(cls, public_only=False):
        me = cls.bot.get_contact()
        groups = []
        for chat in cls.bot.get_chats():
            if cls.bot.is_group(chat):
                if me in chat.get_contacts():
                    if public_only and cls.get_info(chat.id)[2] != PUBLIC:
                        continue
                    groups.append(chat)
        return groups

    @classmethod
    def id_cmd(cls, msg, arg):
        chat = cls.bot.get_chat(msg)
        if cls.bot.is_group(chat):
            pid, topic, status = cls.get_info(chat.id)
            if status == PUBLIC:
                status = _('Group status: {}').format(_('Public'))
                gid = '{}{}'.format(DELTA_URL, chat.id)
            else:
                status = _('Group status: {}').format(_('Private'))
                gid = '{}{}-{}'.format(DELTA_URL, pid, chat.id)
            text = status+'\nID: {}'.format(gid)
        else:
            text = _('Not a group.')
        chat.send_text(text)

    @classmethod
    def public_cmd(cls, msg, arg):
        chat = cls.bot.get_chat(msg)
        status = cls.get_info(chat.id)[2]
        if status != PUBLIC:
            cls.db.execute(
                'UPDATE groups SET status=? WHERE id=?', (PUBLIC, chat.id))
        chat.send_text(_('Group status: {}').format(_('Public')))

    @classmethod
    def private_cmd(cls, msg, arg):
        chat = cls.bot.get_chat(msg)
        status = cls.get_info(chat.id)[2]
        if status != PRIVATE:
            cls.db.execute(
                'UPDATE groups SET status=? WHERE id=?', (PRIVATE, chat.id))
        chat.send_text(_('Group status: {}').format(_('Private')))

    @classmethod
    def topic_cmd(cls, msg, new_topic):
        chat = cls.bot.get_chat(msg)
        topic = cls.get_info(chat.id)[1]
        new_topic = ' '.join(new_topic.split())
        if new_topic:
            if len(new_topic) > 250:
                new_topic = new_topic[:250]+'...'
            topic = new_topic
            cls.db.execute(
                'UPDATE groups SET topic=? WHERE id=?', (topic, chat.id))
        chat.send_text(_('Topic:\n{}').format(topic))

    @classmethod
    def join_cmd(cls, msg, arg):
        chat = cls.bot.get_chat(msg)
        try:
            gid = arg.lstrip(DELTA_URL).split('-')
            pid = ''
            if len(gid) == 2:
                pid = gid[0]
            gid = int(gid.pop())
            for g in cls.get_groups():
                if g.id == gid:
                    pid1, topic, status = cls.get_info(g.id)
                    if status == PUBLIC or pid1 == pid:
                        g.add_contact(msg.get_sender_contact())
                        chat.send_text(_('Added to {} [ID:{}]\n\nTopic:\n{}').format(
                            g.get_name(), g.id, topic))
                        return
                    raise ValueError('Group is private')
        except (ValueError, IndexError) as err:
            cls.bot.logger.exception(err)
            gid = arg
        chat.send_text(_('Unknow group ID: {}').format(gid))

    @classmethod
    def leave_cmd(cls, msg, arg):
        chat = cls.bot.get_chat(msg)
        try:
            if arg:
                gid = int(arg.lstrip(DELTA_URL).split('-').pop())
            else:
                gid = chat.id
            for g in cls.get_groups():
                if g.id == gid and msg.get_sender_contact() in g.get_contacts():
                    g.remove_contact(msg.get_sender_contact())
                    chat.send_text(
                        _('Removed from {} [ID:{}]').format(g.get_name(), g.id))
                    return
        except (ValueError, IndexError) as err:
            cls.bot.logger.exception(err)
            gid = arg
        chat.send_text(_('Unknow group ID: {}').format(gid))

    @classmethod
    def add_cmd(cls, msg, arg):
        try:
            gid, addrs = arg.split(maxsplit=1)
            addrs = [addr.strip()
                     for addr in addrs.strip().split(',') if '@' in addr]
            gid = int(gid.lstrip(DELTA_URL).split('-').pop())
            if not addrs:
                raise ValueError
        except (ValueError, IndexError) as err:
            cls.bot.logger.exception(err)
            chat = cls.bot.get_chat(msg)
            chat.send_text(_('Wrong syntax'))
            return
        for g in cls.get_groups():
            if g.id == gid and msg.get_sender_contact() in g.get_contacts():
                topic = cls.get_info(g.id)[1]
                sender = msg.get_sender_contact().addr
                for addr in addrs:
                    c = cls.bot.get_contact(addr)
                    g.add_contact(c)
                    chat = cls.bot.get_chat(c)
                    chat.send_text(_('Added to {} [ID:{}] by {}\n\nTopic:\n{}').format(
                        g.get_name(), g.id, sender, topic))
                break

    @classmethod
    def remove_cmd(cls, msg, arg):
        try:
            gid, addr = arg.split(maxsplit=1)
            addr = addr.rstrip()
            gid = int(gid.lstrip(DELTA_URL).split('-').pop())
            if '@' not in addr:
                raise ValueError('Invalid email address')
        except (ValueError, IndexError) as err:
            cls.bot.logger.exception(err)
            chat = cls.bot.get_chat(msg)
            chat.send_text(_('Wrong syntax'))
            return
        for g in cls.get_groups():
            if g.id == gid and msg.get_sender_contact() in g.get_contacts():
                # TODO: error if addr not in group
                c = [c for c in cls.bot.account.get_contacts(
                    addr) if c.addr == addr][0]
                g.remove_contact(c)
                sender = msg.get_sender_contact().addr
                chat = cls.bot.get_chat(c)
                chat.send_text(_('Removed from {} [ID:{}] by {}').format(
                    g.get_name(), g.id, sender))
                break

    @classmethod
    def msg_cmd(cls, msg, arg):
        try:
            group_id, text = arg.split(maxsplit=1)
            text = text.rstrip()
            if not text:
                raise ValueError('Missing text argument')
            group_id = int(group_id.lstrip(DELTA_URL).split('-').pop())
        except (ValueError, IndexError) as err:
            cls.bot.logger.exception(err)
            chat = cls.bot.get_chat(msg)
            chat.send_text(_('Wrong syntax'))
            return
        sender = msg.get_sender_contact()
        for g in cls.get_groups():
            if g.id == group_id and sender in g.get_contacts():
                g.send_text('{}:\n{}'.format(sender.addr, text))
                if text.startswith('/'):
                    cls.bot.on_command(msg, text)
                break

    @classmethod
    def list_cmd(cls, msg, arg):
        groups = cls.get_groups(public_only=True)
        groups.sort(key=lambda g: g.get_name())
        for i, g in enumerate(groups):
            topic = cls.get_info(g.id)[1]
            gid = quote_plus('{}{}'.format(DELTA_URL, g.id))
            groups[i] = (g.get_name(), topic, gid, len(g.get_contacts()))
        template = cls.env.get_template('list.html')
        html = template.render(
            plugin=cls, bot_addr=cls.bot.get_address(), groups=groups)
        chat = cls.bot.get_chat(msg)
        cls.bot.send_html(chat, html, cls.name, msg.user_agent)


class DBManager:
    def __init__(self, db_path):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.execute('''CREATE TABLE IF NOT EXISTS groups
                        (id INTEGER NOT NULL,
                         pid TEXT NOT NULL,
                         topic TEXT,
                         status INTEGER,
                         PRIMARY KEY(id))''')

    def execute(self, statement, args=(), get='all'):
        with self.db:
            r = self.db.execute(statement, args)
            return r.fetchall() if get == 'all' else r.fetchone()

    def insert(self, row):
        self.execute('INSERT INTO groups VALUES (?,?,?,?)', row)

    def delete(self, gid):
        self.execute('DELETE FROM groups WHERE id=?', (gid,))

    def close(self):
        self.db.close()
