"""
Pico 2W Asynchronous Control Hub using the refactored WebSocketServer module
"""

import json
import sys

import uasyncio as asyncio
import uselect

try:
	from typing import TYPE_CHECKING
except ImportError:
	TYPE_CHECKING = False

if TYPE_CHECKING:
	from typing import Any, Optional

from ws_server import WebSocketServer

WIFI_SSID = 'Minerva'
WIFI_PASSWORD = 'CezanneZola'

# Initialize WebSocket server with credentials, callback, and port
ws_svr = WebSocketServer(port=8080, ssid=WIFI_SSID, password=WIFI_PASSWORD)


# ==============================================================================
# CORE COMMAND ROUTER
# ==============================================================================
async def handle_incoming_message(
	cmd_str: str, writer: Optional[asyncio.StreamWriter] = None
) -> None:
	"""
	Callback passed into WebSocketServer to process incoming messages.
	For each command, the response will be a dict with mandatory key of
	'type', 'cmd' (which just echoes back the command received) and 'result'.
	There may be other keys depending on the command.
	"""
	response: dict[str, str | int] = {'type': 'none', 'cmd': cmd_str, 'result': 'none'}
	cmd_str = cmd_str.strip()

	if cmd_str == 'STATUS':
		response['type'] = 'STATUS'
		response['clients'] = len(ws_svr.clients)

	elif cmd_str == 'IP':
		response['type'] = 'STATUS'
		response['result'] = f'{ws_svr.ip}'
	else:
		response['type'] = 'ERROR'
		response['result'] = 'Unknown command'

	for key in response:
		print(f'[{key}] {response[key]}')
	if writer is not None:  # respond to specific client
		await ws_svr.send(writer, json.dumps(response))
	else:
		await ws_svr.broadcast(response)


# ==============================================================================
# ASYNCHRONOUS TASK: NON-BLOCKING USB-SERIAL CLI
# ==============================================================================
async def cli_task() -> None:
	"""
	Asynchronous task managing local interactive input over USB CDC Serial.

	Uses `uselect.poll()` to inspect `sys.stdin` non-blockingly. This prevents
	the REPL input reader from freezing the entire system event loop when
	the user isn't typing.

	Incoming bytes are stored in a buffer until a carriage return or newline is
	encountered, at which point the process_command() function is invoked and
	the buffer reset.
	"""
	poll_obj = uselect.poll()
	poll_obj.register(sys.stdin, uselect.POLLIN)
	buffer: str = ''
	print('[CLI] USB Serial CLI ready.')

	while True:
		# Check input stream with zero timeout (non-blocking poll)
		if poll_obj.poll(0):
			char: str | Any = sys.stdin.read(1)
			if char:
				# Handle line termination (Enter key)
				if char == '\n' or char == '\r':
					if buffer:
						sys.stdout.write('\n')
						await handle_incoming_message(buffer)
						buffer = ''
				# Handle backspace key code (ASCII 127)
				elif ord(char) == 127:
					if len(buffer) > 0:
						buffer = buffer[:-1]
						sys.stdout.write('\b \b')  # Visual terminal backspace
				else:
					sys.stdout.write(char)  # Local character echo
					buffer += char
		# Yield execution back to the uasyncio event loop for 20ms
		await asyncio.sleep_ms(20)


# ==============================================================================
# MAIN ENTRY POINT & EVENT LOOP INITIALIZATION
# ==============================================================================
async def main() -> None:
	"""
	Schedules background tasks concurrently inside the primary uasyncio
	event loop.
	"""
	print('\n--- Pico WebSocket Server ---')

	# Assign message callback
	ws_svr.on_message = handle_incoming_message

	# Run WebSocket server and Wi-Fi manager concurrently with the CLI task
	asyncio.create_task(ws_svr.start())
	asyncio.create_task(cli_task())

	while True:
		await asyncio.sleep(1)


try:
	asyncio.run(main())
except KeyboardInterrupt:
	print('\nExecution interrupted. Shutting down...')
