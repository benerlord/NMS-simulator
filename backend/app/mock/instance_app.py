"""
每实例子进程的入口模块。
用法: python -m app.mock.instance_app --topology-id topo_xxx --port 8081 --instance-id inst_xxx [--ssl-certfile cert.pem --ssl-keyfile key.pem]
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
        # 按拓扑所属"网管/设备"（domain）加载接口，一个 domain 下的接口在同域实例间共享。
        # 拓扑无 domain 时（旧数据），退回原按 topology_id 过滤的兼容行为。
        topo_row = conn.execute(
            "SELECT domain_id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        domain_id = topo_row["domain_id"] if topo_row else None
        if domain_id:
            rows = conn.execute(
                "SELECT id, method, path FROM api_configs "
                "WHERE domain_id = ? AND enabled = 1",
                (domain_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, method, path FROM api_configs "
                "WHERE topology_id = ? AND enabled = 1",
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
    parser.add_argument("--ssl-certfile", default=None)
    parser.add_argument("--ssl-keyfile", default=None)
    args = parser.parse_args()

    init_db()
    app = create_app(args.topology_id, instance_id=args.instance_id)

    kwargs = {"host": "0.0.0.0", "port": args.port, "log_level": "warning"}
    if args.ssl_certfile and args.ssl_keyfile:
        kwargs["ssl_certfile"] = args.ssl_certfile
        kwargs["ssl_keyfile"] = args.ssl_keyfile
    uvicorn.run(app, **kwargs)
