import argparse
import json
import logging
import sys
from pathlib import Path

from . import config as cfg_mod
from . import cpi, cutover, inventory, verify, wso2

log = logging.getLogger("pi2cpi")


def _filter(records, names):
    if not names:
        return records
    wanted = set(names)
    return [r for r in records if r.get("name") in wanted]


def cmd_inventory(args):
    client = wso2.Wso2Client(cfg_mod.load_wso2())
    client.authenticate()
    inventory.build_inventory(
        client, names=args.api, only_pi=not args.all, out_dir=args.out,
        swagger_dir=args.swagger_dir, migration_list=args.from_migration_list)


def cmd_generate(args):
    records = _filter(json.loads(Path(args.inventory).read_text(encoding="utf-8")), args.api)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cpi_cfg = cfg_mod.load_cpi(require=bool(args.upload))
    client = None
    if args.upload:
        client = cpi.CpiClient(cpi_cfg)
        client.authenticate()
        client.fetch_csrf()
        client.ensure_package(args.package_id, args.package_name or args.package_id)
    manifest = []
    for rec in records:
        zbytes = cpi.render_iflow(rec, receiver=args.receiver, cpi_path=args.cpi_path)
        iid = cpi.iflow_id(rec["name"])
        path = cpi.sender_path(rec["name"], args.cpi_path)
        (out / f"{iid}.zip").write_bytes(zbytes)
        entry = {"api": rec["name"], "iflow_id": iid, "cpi_path": path}
        if cpi_cfg and cpi_cfg.runtime_url:
            entry["cpi_runtime_url"] = f"{cpi_cfg.runtime_url}/http{path}"
        if client:
            client.upload_iflow(args.package_id, iid, rec["name"], zbytes)
            entry["uploaded"] = True
            if args.deploy:
                client.deploy_iflow(iid)
                entry["deployed"] = True
        manifest.append(entry)
        print(f"{rec['name']} -> {iid}.zip")
    (out / "generate-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def cmd_cutover(args):
    records = _filter(json.loads(Path(args.inventory).read_text(encoding="utf-8")), args.api)
    cpi_cfg = cfg_mod.load_cpi(require=False)
    if not cpi_cfg or not cpi_cfg.runtime_url:
        raise SystemExit("CPI_RUNTIME_URL is not set")
    client = wso2.Wso2Client(cfg_mod.load_wso2())
    if not args.dry_run:
        client.authenticate()
    changes = cutover.plan(client, records, cpi_cfg.runtime_url)
    cutover.apply(client, changes, args.state, dry_run=args.dry_run,
                  include_sandbox=args.include_sandbox)


def cmd_rollback(args):
    client = wso2.Wso2Client(cfg_mod.load_wso2())
    client.authenticate()
    cutover.rollback(client, args.state, names=args.api)


def cmd_verify(args):
    results = verify.verify(
        args.fixtures, args.base_url, names=args.api, path_mode=args.path_mode,
        extra_headers=args.header, ignore_paths=args.ignore_json_path,
        concurrency=args.concurrency, timeout=args.timeout, out_dir=args.out)
    if any(not r["passed"] for r in results):
        sys.exit(1)


def build_parser():
    p = argparse.ArgumentParser(prog="pi2cpi", description="Migrate WSO2/PI backends to SAP CPI")
    p.add_argument("--verbose", "-v", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    inv = sub.add_parser("inventory", help="list WSO2 APIs and classify PI endpoints")
    inv.add_argument("--from-migration-list", metavar="FILE")
    inv.add_argument("--api", action="append")
    inv.add_argument("--all", action="store_true", help="include non-PI APIs")
    inv.add_argument("--out", default=".")
    inv.add_argument("--swagger-dir")
    inv.set_defaults(func=cmd_inventory)

    gen = sub.add_parser("generate", help="render CPI iFlow zips from inventory")
    gen.add_argument("--inventory", default="inventory.json")
    gen.add_argument("--api", action="append")
    gen.add_argument("--out", default="iflows")
    gen.add_argument("--receiver", choices=["soap", "rfc"], default="soap")
    gen.add_argument("--cpi-path", help="override sender URL path")
    gen.add_argument("--upload", action="store_true")
    gen.add_argument("--package-id")
    gen.add_argument("--package-name")
    gen.add_argument("--deploy", action="store_true")
    gen.set_defaults(func=cmd_generate)

    cut = sub.add_parser("cutover", help="point WSO2 endpoints at CPI")
    cut.add_argument("--inventory", default="inventory.json")
    cut.add_argument("--api", action="append")
    cut.add_argument("--include-sandbox", action="store_true")
    cut.add_argument("--dry-run", action="store_true")
    cut.add_argument("--state", default="cutover-state.json")
    cut.set_defaults(func=cmd_cutover)

    rb = sub.add_parser("rollback", help="restore original endpoints")
    rb.add_argument("--api", action="append")
    rb.add_argument("--state", default="cutover-state.json")
    rb.set_defaults(func=cmd_rollback)

    vf = sub.add_parser("verify", help="replay fixtures against a base URL")
    vf.add_argument("--fixtures", required=True)
    vf.add_argument("--base-url", required=True)
    vf.add_argument("--api", action="append")
    vf.add_argument("--path-mode", choices=["wso2", "cpi"], default="wso2")
    vf.add_argument("--header", action="append", help="K:V, repeatable")
    vf.add_argument("--ignore-json-path", action="append")
    vf.add_argument("--concurrency", type=int, default=4)
    vf.add_argument("--timeout", type=float, default=60)
    vf.add_argument("--out", default=".")
    vf.set_defaults(func=cmd_verify)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        log.error("%s", e, exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
