import json

from tornado.concurrent import Future

from jupyter_server.base.zmqhandlers import (
    serialize_binary_message, 
    deserialize_binary_message    
)


class ZMQChannels:

    zmq_stream: str = None
    channels: dict = {}
    kernel_id: str = None
    kernel_info_channel: str = None
    _kernel_info_future = Future()
    _close_future = Future()
    session_key: str = ''
    _iopub_window_msg_count: int = 0
    _iopub_window_byte_count: int = 0
    _iopub_msgs_exceeded: bool = False
    _iopub_data_exceeded: bool = False
    _iopub_window_byte_queue: list = []
    _open_sessions = {}

    def __init__(self, *args, **kwargs):
        super(ZMQWebsocket, self).__init__(self, *args, **kwargs)
        self.session = Session(config=self.config)

    @property
    def config(self):
        return router.app.config

    @property
    def app(self):
        return router.app

    @property
    def log(self):
        return router.app.log

    @property
    def kernel_manager(self):
        return router.app.kernel_manager

    @property
    def kernel_info_timeout(self):
        km_default = self.kernel_manager.kernel_info_timeout
        return app.tornado_settings.get('kernel_info_timeout', km_default)

    @property
    def iopub_msg_rate_limit(self):
        return app.tornado_settings.get('iopub_msg_rate_limit', 0)

    @property
    def iopub_data_rate_limit(self):
        return app.tornado_settings.get('iopub_data_rate_limit', 0)

    @property
    def rate_limit_window(self):
        return app.tornado_settings.get('rate_limit_window', 1.0)

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, getattr(self, 'kernel_id', 'uninitialized'))

    def create_stream(self):
        km = self.kernel_manager
        identity = self.session.bsession
        for channel in ('shell', 'control', 'iopub', 'stdin'):
            meth = getattr(km, 'connect_' + channel)
            self.channels[channel] = stream = meth(self.kernel_id, identity=identity)
            stream.channel = channel

    def request_kernel_info(self):
        """send a request for kernel_info"""
        km = self.kernel_manager
        kernel = km.get_kernel(self.kernel_id)
        try:
            # check for previous request
            future = kernel._kernel_info_future
        except AttributeError:
            self.log.debug("Requesting kernel info from %s", self.kernel_id)
            # Create a kernel_info channel to query the kernel protocol version.
            # This channel will be closed after the kernel_info reply is received.
            if self.kernel_info_channel is None:
                self.kernel_info_channel = km.connect_shell(self.kernel_id)
            self.kernel_info_channel.on_recv(self._handle_kernel_info_reply)
            self.session.send(self.kernel_info_channel, "kernel_info_request")
            # store the future on the kernel, so only one request is sent
            kernel._kernel_info_future = self._kernel_info_future
        else:
            if not future.done():
                self.log.debug("Waiting for pending kernel_info request")
            future.add_done_callback(lambda f: self._finish_kernel_info(f.result()))
        return self._kernel_info_future

    def _handle_kernel_info_reply(self, msg):
        """process the kernel_info_reply

        enabling msg spec adaptation, if necessary
        """
        idents,msg = self.session.feed_identities(msg)
        try:
            msg = self.session.deserialize(msg)
        except:
            self.log.error("Bad kernel_info reply", exc_info=True)
            self._kernel_info_future.set_result({})
            return
        else:
            info = msg['content']
            self.log.debug("Received kernel info: %s", info)
            if msg['msg_type'] != 'kernel_info_reply' or 'protocol_version' not in info:
                self.log.error("Kernel info request failed, assuming current %s", info)
                info = {}
            self._finish_kernel_info(info)

        # close the kernel_info channel, we don't need it anymore
        if self.kernel_info_channel:
            self.kernel_info_channel.close()
        self.kernel_info_channel = None

    def _finish_kernel_info(self, info):
        """Finish handling kernel_info reply

        Set up protocol adaptation, if needed,
        and signal that connection can continue.
        """
        protocol_version = info.get('protocol_version', client_protocol_version)
        if protocol_version != client_protocol_version:
            self.session.adapt_version = int(protocol_version.split('.')[0])
            self.log.info("Adapting from protocol version {protocol_version} (kernel {kernel_id}) to {client_protocol_version} (client).".format(protocol_version=protocol_version, kernel_id=self.kernel_id, client_protocol_version=client_protocol_version))
        if not self._kernel_info_future.done():
            self._kernel_info_future.set_result(info)

    # async def pre_get(self):
    #     # authenticate first
    #     super(ZMQChannelsHandler, self).pre_get()
    #     # check session collision:
    #     await self._register_session()
    #     # then request kernel info, waiting up to a certain time before giving up.
    #     # We don't want to wait forever, because browsers don't take it well when
    #     # servers never respond to websocket connection requests.
    #     kernel = self.kernel_manager.get_kernel(self.kernel_id)
    #     self.session.key = kernel.session.key
    #     future = self.request_kernel_info()

    #     def give_up():
    #         """Don't wait forever for the kernel to reply"""
    #         if future.done():
    #             return
    #         self.log.warning("Timeout waiting for kernel_info reply from %s", self.kernel_id)
    #         future.set_result({})
    #     loop = IOLoop.current()
    #     loop.add_timeout(loop.time() + self.kernel_info_timeout, give_up)
    #     # actually wait for it
    #     await future

    async def get(self, kernel_id):
        self.kernel_id = cast_unicode(kernel_id, 'ascii')
        await super(ZMQChannelsHandler, self).get(kernel_id=kernel_id)

    async def _register_session(self):
        """Ensure we aren't creating a duplicate session.

        If a previous identical session is still open, close it to avoid collisions.
        This is likely due to a client reconnecting from a lost network connection,
        where the socket on our side has not been cleaned up yet.
        """
        self.session_key = '%s:%s' % (self.kernel_id, self.session.session)
        stale_handler = self._open_sessions.get(self.session_key)
        if stale_handler:
            self.log.warning("Replacing stale connection: %s", self.session_key)
            await stale_handler.close()
        self._open_sessions[self.session_key] = self

    def open(self, kernel_id):
        super(ZMQChannelsHandler, self).open()
        km = self.kernel_manager
        km.notify_connect(kernel_id)

        # on new connections, flush the message buffer
        buffer_info = km.get_buffer(kernel_id, self.session_key)
        if buffer_info and buffer_info['session_key'] == self.session_key:
            self.log.info("Restoring connection for %s", self.session_key)
            self.channels = buffer_info['channels']
            replay_buffer = buffer_info['buffer']
            if replay_buffer:
                self.log.info("Replaying %s buffered messages", len(replay_buffer))
                for channel, msg_list in replay_buffer:
                    stream = self.channels[channel]
                    self._on_zmq_reply(stream, msg_list)
        else:
            try:
                self.create_stream()
            except web.HTTPError as e:
                self.log.error("Error opening stream: %s", e)
                # WebSockets don't response to traditional error codes so we
                # close the connection.
                for channel, stream in self.channels.items():
                    if not stream.closed():
                        stream.close()
                self.close()
                return

        km.add_restart_callback(self.kernel_id, self.on_kernel_restarted)
        km.add_restart_callback(self.kernel_id, self.on_restart_failed, 'dead')

        for channel, stream in self.channels.items():
            stream.on_recv_stream(self._on_zmq_reply)

    def on_message(self, msg):
        if not self.channels:
            # already closed, ignore the message
            self.log.debug("Received message on closed websocket %r", msg)
            return
        if isinstance(msg, bytes):
            msg = deserialize_binary_message(msg)
        else:
            msg = json.loads(msg)
        channel = msg.pop('channel', None)
        if channel is None:
            self.log.warning("No channel specified, assuming shell: %s", msg)
            channel = 'shell'
        if channel not in self.channels:
            self.log.warning("No such channel: %r", channel)
            return
        am = self.kernel_manager.allowed_message_types
        mt = msg['header']['msg_type']
        if am and mt not in am:
            self.log.warning('Received message of type "%s", which is not allowed. Ignoring.' % mt)
        else:
            stream = self.channels[channel]
            self.session.send(stream, msg)

    def _on_zmq_reply(self, stream, msg_list):
        idents, fed_msg_list = self.session.feed_identities(msg_list)
        msg = self.session.deserialize(fed_msg_list)
        parent = msg['parent_header']
        def write_stderr(error_message):
            self.log.warning(error_message)
            msg = self.session.msg("stream",
                content={"text": error_message + '\n', "name": "stderr"},
                parent=parent
            )
            msg['channel'] = 'iopub'
            self.write_message(json.dumps(msg, default=date_default))
        channel = getattr(stream, 'channel', None)
        msg_type = msg['header']['msg_type']

        if channel == 'iopub' and msg_type == 'status' and msg['content'].get('execution_state') == 'idle':
            # reset rate limit counter on status=idle,
            # to avoid 'Run All' hitting limits prematurely.
            self._iopub_window_byte_queue = []
            self._iopub_window_msg_count = 0
            self._iopub_window_byte_count = 0
            self._iopub_msgs_exceeded = False
            self._iopub_data_exceeded = False

        if channel == 'iopub' and msg_type not in {'status', 'comm_open', 'execute_input'}:

            # Remove the counts queued for removal.
            now = IOLoop.current().time()
            while len(self._iopub_window_byte_queue) > 0:
                queued = self._iopub_window_byte_queue[0]
                if (now >= queued[0]):
                    self._iopub_window_byte_count -= queued[1]
                    self._iopub_window_msg_count -= 1
                    del self._iopub_window_byte_queue[0]
                else:
                    # This part of the queue hasn't be reached yet, so we can
                    # abort the loop.
                    break

            # Increment the bytes and message count
            self._iopub_window_msg_count += 1
            if msg_type == 'stream':
                byte_count = sum([len(x) for x in msg_list])
            else:
                byte_count = 0
            self._iopub_window_byte_count += byte_count

            # Queue a removal of the byte and message count for a time in the
            # future, when we are no longer interested in it.
            self._iopub_window_byte_queue.append((now + self.rate_limit_window, byte_count))

            # Check the limits, set the limit flags, and reset the
            # message and data counts.
            msg_rate = float(self._iopub_window_msg_count) / self.rate_limit_window
            data_rate = float(self._iopub_window_byte_count) / self.rate_limit_window

            # Check the msg rate
            if self.iopub_msg_rate_limit > 0 and msg_rate > self.iopub_msg_rate_limit:
                if not self._iopub_msgs_exceeded:
                    self._iopub_msgs_exceeded = True
                    write_stderr(dedent("""\
                    IOPub message rate exceeded.
                    The Jupyter server will temporarily stop sending output
                    to the client in order to avoid crashing it.
                    To change this limit, set the config variable
                    `--ServerApp.iopub_msg_rate_limit`.

                    Current values:
                    ServerApp.iopub_msg_rate_limit={} (msgs/sec)
                    ServerApp.rate_limit_window={} (secs)
                    """.format(self.iopub_msg_rate_limit, self.rate_limit_window)))
            else:
                # resume once we've got some headroom below the limit
                if self._iopub_msgs_exceeded and msg_rate < (0.8 * self.iopub_msg_rate_limit):
                    self._iopub_msgs_exceeded = False
                    if not self._iopub_data_exceeded:
                        self.log.warning("iopub messages resumed")

            # Check the data rate
            if self.iopub_data_rate_limit > 0 and data_rate > self.iopub_data_rate_limit:
                if not self._iopub_data_exceeded:
                    self._iopub_data_exceeded = True
                    write_stderr(dedent("""\
                    IOPub data rate exceeded.
                    The Jupyter server will temporarily stop sending output
                    to the client in order to avoid crashing it.
                    To change this limit, set the config variable
                    `--ServerApp.iopub_data_rate_limit`.

                    Current values:
                    ServerApp.iopub_data_rate_limit={} (bytes/sec)
                    ServerApp.rate_limit_window={} (secs)
                    """.format(self.iopub_data_rate_limit, self.rate_limit_window)))
            else:
                # resume once we've got some headroom below the limit
                if self._iopub_data_exceeded and data_rate < (0.8 * self.iopub_data_rate_limit):
                    self._iopub_data_exceeded = False
                    if not self._iopub_msgs_exceeded:
                        self.log.warning("iopub messages resumed")

            # If either of the limit flags are set, do not send the message.
            if self._iopub_msgs_exceeded or self._iopub_data_exceeded:
                # we didn't send it, remove the current message from the calculus
                self._iopub_window_msg_count -= 1
                self._iopub_window_byte_count -= byte_count
                self._iopub_window_byte_queue.pop(-1)
                return
        super(ZMQChannelsHandler, self)._on_zmq_reply(stream, msg)

    def close(self):
        super(ZMQChannelsHandler, self).close()
        return self._close_future

    def on_close(self):
        self.log.debug("Websocket closed %s", self.session_key)
        # unregister myself as an open session (only if it's really me)
        if self._open_sessions.get(self.session_key) is self:
            self._open_sessions.pop(self.session_key)

        km = self.kernel_manager
        if self.kernel_id in km:
            km.notify_disconnect(self.kernel_id)
            km.remove_restart_callback(
                self.kernel_id, self.on_kernel_restarted,
            )
            km.remove_restart_callback(
                self.kernel_id, self.on_restart_failed, 'dead',
            )

            # start buffering instead of closing if this was the last connection
            if km._kernel_connections[self.kernel_id] == 0:
                km.start_buffering(self.kernel_id, self.session_key, self.channels)
                self._close_future.set_result(None)
                return

        # This method can be called twice, once by self.kernel_died and once
        # from the WebSocket close event. If the WebSocket connection is
        # closed before the ZMQ streams are setup, they could be None.
        for channel, stream in self.channels.items():
            if stream is not None and not stream.closed():
                stream.on_recv(None)
                stream.close()

        self.channels = {}
        self._close_future.set_result(None)

    def _send_status_message(self, status):
        iopub = self.channels.get('iopub', None)
        if iopub and not iopub.closed():
            # flush IOPub before sending a restarting/dead status message
            # ensures proper ordering on the IOPub channel
            # that all messages from the stopped kernel have been delivered
            iopub.flush()
        msg = self.session.msg("status",
            {'execution_state': status}
        )
        msg['channel'] = 'iopub'
        self.write_message(json.dumps(msg, default=date_default))

    def on_kernel_restarted(self):
        logging.warn("kernel %s restarted", self.kernel_id)
        self._send_status_message('restarting')

    def on_restart_failed(self):
        logging.error("kernel %s restarted failed!", self.kernel_id)
        self._send_status_message('dead')
