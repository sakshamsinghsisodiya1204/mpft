"""Entry point for `python -m mpft web`: peer server (0.0.0.0) in a thread, UI server (127.0.0.1) in front."""
import uvicorn

from .node import Node
from .peer import make_peer_app
from .serve import start_in_thread
from .ui import make_ui_app


def run_web(a):
    node = Node(a.name, a.peer_port, a.out, a.host, a.rendezvous, a.max_size)
    start_in_thread(make_peer_app(node), "0.0.0.0", a.peer_port)
    print(f"{a.name}: UI http://127.0.0.1:{a.ui_port}  peer :{a.peer_port}  Receiver ID {node.id}", flush=True)
    uvicorn.run(make_ui_app(node, a.ui_port), host="127.0.0.1", port=a.ui_port, log_level="warning",
                timeout_graceful_shutdown=2)  # open SSE streams must not block Ctrl-C
