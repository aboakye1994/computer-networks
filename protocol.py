import json
import time
from enum import Enum

class MessageType(str, Enum):
    COMMAND = "command"
    RESPONSE = "response"
    EVENT = "event"

class CommandName(str, Enum):
    """Commands that travel on the wire (client -> server)."""

    CONNECT = "connect" #/connect <server-name> [port#]
    NICK = "nick"      # /nick <nickname>
    LIST = "list"      # /list
    JOIN = "join"      # /join <channel>
    LEAVE = "leave"    # /leave [<channel>]
    QUIT = "quit"      # /quit
    HELP = "help"      # /help
    MSG = "msg"        # plain chat text after joining a channel


class EventName(str, Enum):
    """Events that the server sends to clients (server -> client)."""

    MESSAGE = "message"          # someone sent a chat message
    USER_JOINED = "user_joined"  # user joined a channel
    USER_LEFT = "user_left"      # user left a channel
    SERVER_SHUTDOWN = "server_shutdown"

# Core message object

class Message:
    """
    In-memory representation of a protocol message.

    'data' must be JSON-serializable.
    """

    def __init__(self, type, name, data):
        # Store the message fields.
        self.type = type   #e.g. MessageType.COMMAND
        self.name = name   #e.g. "join"
        self.data = data   #e.g. {"channel": "cats"

    def to_dict(self):
        """
        Convert the Message object into a JSON-serializable dictionary.
        """
        return {
            "type": self.type.value,  # "command" / "response" / "event"
            "name": self.name,    # "join", "msg", etc.
            "data": self.data,   #payload dict
        }

    @classmethod
    def from_dict(cls, raw):
        """
        Build a Message instance from a dictionary received over the network.
        """
        try:
            mtype = MessageType(raw["type"])
            name = raw["name"]
            data = raw.get("data", {}) or {}
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Invalid message object: {raw!r}") from e

        return cls(mtype, name, data)

    def __repr__(self):
        """
        String representation for debugging.
        """
        return f"Message(type={self.type!r}, name={self.name!r}, data={self.data!r})"


# Protocol helpers

class Protocol:
    """
    Static helpers for encoding/decoding messages and constructing
    standard command/response/event objects.
    """

    #wire encoding / decoding

    @staticmethod
    def encode(msg):
        """
        Encode a Message -> bytes suitable for sending on a socket.

        Uses newline-delimited JSON (NDJSON):
            b'{"type":"command","name":"join","data":{"channel":"cats"}}\\n'
        """
        text = json.dumps(msg.to_dict(), separators=(",", ":"))
        return (text + "\n").encode("utf-8")

    @staticmethod
    def decode(line):
        """
        Decode a line of text or bytes from the wire into a Message.

        Caller is responsible for reading a full line (ending in '\\n').
        """
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from peer: {line!r}") from e
        return Message.from_dict(raw)

    #commands (client -> server)

    @staticmethod
    def cmd_connect(server, port=6667):
        """
        /connect <server> <port#>
        Connect to a chat server.
        """
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.CONNECT.value,
            data={"server": server, "port": port},
        )

    @staticmethod
    def cmd_nick(nickname):
        """
        /nick <nickname>
        """
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.NICK.value,
            data={"nickname": nickname},
        )

    @staticmethod
    def cmd_list():
        """
        /list
        """
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.LIST.value,
            data={},
        )

    @staticmethod
    def cmd_join(channel):
        """
        /join <channel>
        """
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.JOIN.value,
            data={"channel": channel},
        )

    @staticmethod
    def cmd_leave(channel=None):
        """
        /leave [<channel>]
        If channel is None, leave the client's current channel.
        """
        data = {}
        if channel:
            data["channel"] = channel
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.LEAVE.value,
            data=data,
        )

    @staticmethod
    def cmd_quit(reason=None):
        """
        /quit
        """
        data = {}
        if reason:
            data["reason"] = reason
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.QUIT.value,
            data=data,
        )

    @staticmethod
    def cmd_help():
        """
        /help
        """
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.HELP.value,
            data={},
        )

    @staticmethod
    def cmd_msg(text, channel=None):
        """
        Plain chat text (after /join).

        The client should call this whenever the user types a non-slash line.
        If channel is None, the server should treat it as the client's current channel.
        """
        data = {"text": text}
        if channel:
            data["channel"] = channel
        return Message(
            type=MessageType.COMMAND,
            name=CommandName.MSG.value,
            data=data,
        )

    #responses (server -> client)

    @staticmethod
    def resp_ok(command_name, data=None):
        """
        Generic success response:

        {
            "type": "response",
            "name": "<command_name>",
            "data": {
                "status": "ok",
                ...
            }
        }
        """
        return Message(
            type=MessageType.RESPONSE,
            name=command_name,
            data={"status": "ok", **(data or {})},
        )

    @staticmethod
    def resp_error(command_name, error_msg, data=None):
        """
        Generic error response:

        {
            "type": "response",
            "name": "<command_name>",
            "data": {
                "status": "error",
                "error": "<error_msg>",
                ...
            }
        }
        """
        base = {"status": "error", "error": error_msg}
        if data:
            base.update(data)
        return Message(
            type=MessageType.RESPONSE,
            name=command_name,
            data=base,
        )

    @staticmethod
    def resp_connected(server_name, client_id, motd=None):
        """
        Response to /connect - confirms successful connection.

        server_name: name/address of the server
        client_id: client id
        motd: optional message of the day
        """
        data = {
            "server": server_name,
            "client_id": client_id,
        }
        if motd:
            data["motd"] = motd
        return Protocol.resp_ok(
            CommandName.CONNECT.value,
            data
        )

    @staticmethod
    def resp_list_channels(channels):
        """
        Response to /list.

        channels: list of {"name": "#channel", "users": <int>}
        """
        return Protocol.resp_ok(
            CommandName.LIST.value,
            {"channels": channels},
        )

    @staticmethod
    def resp_help(commands):
        """
        Response to /help.

        commands: list of supported commands as human-readable strings.
        """
        return Protocol.resp_ok(
            CommandName.HELP.value,
            {"commands": commands},
        )

    # events (server -> client)

    @staticmethod
    def evt_message(channel, sender, text, timestamp=None):
        """
        Event: someone sent a message to a channel.

        {
            "type": "event",
            "name": "message",
            "data": {
                "channel": "#cats",
                "from": "Angel",
                "text": "hello",
                "timestamp": 1732305580.123   # optional
            }
        }
        """
        payload = {
            "channel": channel,
            "from": sender,
            "text": text,
            "timestamp": timestamp or time.time(), #Defaults to now
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        return Message(
            type=MessageType.EVENT,
            name=EventName.MESSAGE.value,
            data=payload,
        )

    @staticmethod
    def evt_user_joined(channel, username):
        """
        Event: a user joined a channel.
        """
        return Message(
            type=MessageType.EVENT,
            name=EventName.USER_JOINED.value,
            data={"channel": channel, "user": username},
        )

    @staticmethod
    def evt_user_left(channel, username):
        """
        Event: a user left a channel.
        """
        return Message(
            type=MessageType.EVENT,
            name=EventName.USER_LEFT.value,
            data={"channel": channel, "user": username},
        )

    @staticmethod
    def evt_server_shutdown(reason=None):
        """
        Event: server is shutting down.
        """
        data = {}
        if reason:
            data["reason"] = reason
        return Message(
            type=MessageType.EVENT,
            name=EventName.SERVER_SHUTDOWN.value,
            data=data,
        )