# PICO_WS_MP

This is MicroPython code to create a WebSockets server on a Raspberry Pi Pico 2W.

This was created mainly as a way of playing around with WebSockets.

The wifi connection and WebSocket functionality have been moved to a class. As this is in a separate file, make sure you upload both `main.py` and `ws_server.py` to the Pico.

The WebSockets code supports multiple clients because ... why not? Output to the clients consists of broadcasting the same messages to all those currently connected.

There are, in fact, two ways of communicating with the Pico. There's WebSockets (duh) and a CLI via the Pico's USB. Responses from the Pico get sent to both channels.

## WEBCLIENT

I've included a simple web client to show how you might communicate with the Pico. It's basic but (as far as I know) functional and should provide a good starting point.

![Web client](img/WS_Client_simple.png)

This repo was set up to support an article on [_Machina Speculatrix_](https://medium.com/machina-speculatrix) (Medium subscription required).

## REFERENCES

- [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/info/rfc6455/).
- [WebSocket Protocol: RFC 6455 Handshake, Frames & More](https://websocket.org/guides/websocket-protocol/).
