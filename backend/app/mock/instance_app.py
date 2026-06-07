"""
每实例子进程的入口模块。
用法: python -m app.mock.instance_app --topology-id topo_xxx --port 8081 --instance-id inst_xxx
"""


def create_app(topology_id: str, instance_id: str = None):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.db.connection import connect
    from app.mock.handler import make_handler

    app = FastAPI(title=f"Mock Instance [{topology_id}]")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, method, path FROM api_configs WHERE topology_id = ? AND enabled = 1",
            (topology_id,),
        ).fetchall()

    for row in rows:
        handler = make_handler(row["id"], instance_id=instance_id)
        app.add_api_route(
            path=row["path"],
            endpoint=handler,
            methods=[row["method"]],
        )

    return app


if __name__ == "__main__":
    import argparse
    import uvicorn
    from app.db.connection import init_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--topology-id", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--instance-id", default=None)
    args = parser.parse_args()

    init_db()
    app = create_app(args.topology_id, instance_id=args.instance_id)
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
