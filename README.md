# Chat Protocol

Object-based communication protocol for the chat server/client system using newline-delimited JSON (NDJSON).

## Team Members

| Name | Role | Contribution |
|------|------|--------------|
| Angel Boakye | Protocol Designer | Designed the full object-based protocol and wrote the protocol documentation. |
| Natalie Hwang | Server Designer | Built the multi-threaded chat server with channel management, event broadcasting, and command handling. |
| Jainishkumar Patel | Client Designer | Implemented the interactive chat client with command parsing, event handling, and connection logic. |
| A.Y. Sodipe | Testing & Documentation | Created the full test plan, executed all tests, recorded the demo video, and completed all final README sections. |

## Demo Video

A 5-minute demonstration of our chat system can be viewed here:

👉 **Demo Video:** https://your-video-link-here.com


## Overview

This protocol provides a simple, text-based messaging format for client-server communication. All messages are JSON objects sent over TCP sockets, terminated by newlines.

## Project Structure / File Manifest

```text
computer-networks/
│
├── chat_server.py        # Multi-threaded chat server (channels, events, commands, idle timeout)
├── chat_client.py        # Interactive client (command parser, receiver thread, event handler)
├── protocol.py           # NDJSON object-based protocol for commands, responses, and events
└── README.md             # Full project documentation and test results


```
## Building and Running

### Requirements
- Python 3.10+
- No external libraries required
- Works on Windows, macOS, and Linux

---

### Running the Server

Start the server by specifying a port and optional debug level:

```bash
python3 chat_server.py -p 5000 -d 1
```

## Message Structure

Every message has three fields:

```json
{
  "type": "command|response|event",
  "name": "message_name",
  "data": { /* message-specific fields */ }
}
```

## Message Types

### Commands (Client → Server)
- `connect` - Connect to server
- `nick` - Set nickname
- `list` - List channels
- `join` - Join a channel
- `leave` - Leave a channel
- `msg` - Send chat message
- `help` - Get help
- `quit` - Disconnect

### Responses (Server → Client)
- Success: `{"status": "ok", ...}`
- Error: `{"status": "error", "error": "message", ...}`

### Events (Server → Client)
- `message` - Chat message broadcast
- `user_joined` - User joined channel
- `user_left` - User left channel
- `server_shutdown` - Server shutting down

## Quick Start

```python
from protocol import Protocol, Message

# Create a command
msg = Protocol.cmd_join("#general")

# Encode for network transmission
data = Protocol.encode(msg)  # Returns bytes ending in \n

# Check message type
if msg.type == MessageType.RESPONSE:
    if msg.data.get("status") == "ok":
        print("Success!")
```

## Wire Format

Messages are sent as newline-delimited JSON:

```
{"type":"command","name":"join","data":{"channel":"#general"}}\n
{"type":"response","name":"join","data":{"status":"ok"}}\n
{"type":"event","name":"message","data":{"channel":"#general","from":"Alice","text":"Hello!"}}\n
```

## Examples

### Client connects and joins a channel

```python
# 1. Connect
msg = Protocol.cmd_connect("chat.example.com", 6667)
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"connect","data":{"status":"ok","server":"chat.example.com","client_id":"client-123"}}

# 2. Set nickname
msg = Protocol.cmd_nick("Alice")
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"nick","data":{"status":"ok"}}

# 3. Join channel
msg = Protocol.cmd_join("#general")
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"join","data":{"status":"ok"}}

# 4. Send message
msg = Protocol.cmd_msg("Hello everyone!")
sock.sendall(Protocol.encode(msg))

# All users receive: {"type":"event","name":"message","data":{"channel":"#general","from":"Alice","text":"Hello everyone!"}}
```

### Error handling

```python
msg = Protocol.cmd_nick("@invalid@")
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"nick","data":{"status":"error","error":"Invalid nickname format"}}
```

## Validation Rules

- **Nicknames**: 1-20 characters, alphanumeric and underscores only
- **Channel names**: Must start with `#`, 2-50 characters
- **Messages**: No embedded newlines, max 512 bytes recommended

## Implementation Notes

- **Encoding**: UTF-8
- **Line terminator**: `\n` (newline)
- **Buffering**: Socket reads may be partial; buffer until `\n` is found
- **Message size**: Keep under 4KB for reliability
- **Text content**: Must not contain literal newlines (escape or reject)

## API Reference

### Factory Methods

```python
# Commands
Protocol.cmd_connect(server, port=6667)
Protocol.cmd_nick(nickname)
Protocol.cmd_list()
Protocol.cmd_join(channel)
Protocol.cmd_leave(channel=None)
Protocol.cmd_msg(text, channel=None)
Protocol.cmd_help()
Protocol.cmd_quit(reason=None)

# Responses
Protocol.resp_ok(command_name, data=None)
Protocol.resp_error(command_name, error_msg, data=None)
Protocol.resp_connected(server_name, client_id, motd=None)
Protocol.resp_list_channels(channels)
Protocol.resp_help(commands)

# Events
Protocol.evt_message(channel, sender, text, timestamp=None)
Protocol.evt_user_joined(channel, username)
Protocol.evt_user_left(channel, username)
Protocol.evt_server_shutdown(reason=None)
```

## Testing
All tests were executed using the final multi-threaded server (`chat_server.py`) and the interactive client (`chat_client.py`). All communication used the newline-delimited JSON protocol defined in `protocol.py`.

### Test Environment
- OS: Windows 11 / macOS / Linux  
- Python 3.10+  
- Server started with:
   ```
  python3 chat_server.py -p 5000 -d 1
   
  ```

- Clients run with:
  ```
  python3 chat_client.py
  ```



---

## Test Categories & Results

### 1. Connection

| Test | Expected | Result |
|------|----------|--------|
| `/connect localhost 5000` | Server returns `resp_connected` + MOTD | Passed |
| Bad port | Client shows error and does not crash | Passed |
| Double connect | Warning printed, no crash | Passed |

---

### 2. Nickname Tests

| Test | Expected | Result |
|------|----------|--------|
| `/nick AY` | Nickname updated | Passed |
| Duplicate nickname | Error: "Nickname already in use" | Passed |
| Invalid nickname | Error: "Invalid nickname format" | Passed |

---

### 3. Channel Operations

| Test | Expected | Result |
|------|----------|--------|
| `/join #rockets` | Join success + join event broadcast | Passed |
| `/leave` (in channel) | Leaves first active channel | Passed |
| `/leave` (not in channel) | Error returned | Passed |
| `/list` | Channels + user counts displayed | Passed |

---

### 4. Messaging

| Test | Expected | Result |
|------|----------|--------|
| Sending chat text | `[channel] sender: text` printed | Passed |
| Send without joining | Client error message | Passed |
| Cross-channel isolation | No leakage between channels | Passed |

---

### 5. Multithreading

| Expected | Result |
|----------|--------|
| 4 clients sending messages | No deadlocks or crashes | Passed |
| Thread limit (4) respected | Passed |

---

### 6. Idle Timeout

| Expected | Result |
|----------|--------|
| Server auto-shuts down after ~180 seconds with 0 clients | Passed |

---

### 7. Ctrl-C Shutdown

| Expected | Result |
|----------|--------|
| Server broadcasts `SERVER_SHUTDOWN` event and disconnects all clients | Passed |

---

## Observations & Reflection

- The JSON-based protocol made debugging and testing easier due to predictable structured messages.
- Multi-threading with a fixed 4-thread semaphore prevented overload and maintained stability throughout testing.
- JOIN/LEAVE operations consistently updated channel state correctly in both client and server.
- The client sets `current_channel` optimistically before server confirmation; during testing, server responses corrected any mismatches.
- Idle shutdown reliably triggered after 3 minutes when no clients were connected.
- Ctrl-C graceful shutdown prevented socket leaks and ensured clean program termination.
- All required functionality behaved consistently across Windows, macOS, and Linux.

This testing confirmed that the system meets all core project requirements.

## GenAI Usage Disclosure

Portions of this project’s documentation and testing plan were generated or refined using AI assistance (ChatGPT).  
All source code in `chat_server.py`, `chat_client.py`, and `protocol.py` was written and debugged by the team members.  
A separate file containing our interaction history is included as required.


## License

Created for CSC4220 Computer Networks Team Project.
