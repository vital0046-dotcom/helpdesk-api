"""Replay this project's Postman collection against a running demo API."""

import argparse
import json
import re
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    collection = json.loads(
        (
            Path(__file__).resolve().parents[1] / "examples/helpdesk.postman_collection.json"
        ).read_text(encoding="utf-8")
    )
    variables = {"base_url": args.base_url.rstrip("/")}

    def expand(value):
        return re.sub(
            r"\{\{(.*?)\}\}",
            lambda match: str(uuid.uuid4()) if match[1] == "$guid" else str(variables[match[1]]),
            value,
        )

    for item in collection["item"]:
        request = item["request"]
        body = request.get("body", {}).get("raw")
        headers = {h["key"]: h["value"] for h in request.get("header", [])}
        req = Request(
            expand(request["url"]),
            data=expand(body).encode() if body is not None else None,
            headers=headers,
            method=request["method"],
        )
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            status, raw = response.status, response.read()
        scripts = "\n".join(item["event"][0]["script"]["exec"])
        expected = int(re.search(r"\.status\((\d+)\)", scripts)[1])
        if status != expected:
            raise RuntimeError(f"{item['name']}: expected {expected}, got {status}: {raw!r}")
        for variable in re.findall(r'pm.collectionVariables.set\("(.*?)",', scripts):
            variables[variable] = json.loads(raw)["id"]
        print(f"{item['name']}: HTTP {status} OK")
    print(f"Passed {len(collection['item'])} requests")


if __name__ == "__main__":
    main()
