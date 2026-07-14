"""
energov_probe.py — DEBUG ONLY. Probe Tyler EnerGov Citizen Self Service
portals (Albemarle County, City of Fredericksburg) to determine whether
anonymous permit search works and what the JSON API expects.

Not wired into the pipeline. Run from GitHub Actions via the Scraper
Debug workflow:  scraper input = energov_probe
"""
import json
import logging

import httpx

log = logging.getLogger(__name__)

TENANTS = {
    "albemarle": "https://albemarlecountyva-energovweb.tylerhost.net/apps/selfservice",
    "fredericksburg": "https://selfservice.fredericksburgva.gov/energov_prod/selfservice",
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SEARCH_BODIES = [
    # Modern CSS global search payload
    {
        "Keyword": "", "ExactMatch": True, "SearchModule": 2,
        "FilterModule": 1, "SearchMainAddress": False,
        "PageNumber": 1, "PageSize": 10,
        "SortBy": "IssuedDate", "SortAscending": False,
    },
    # Older shape with explicit criteria wrapper
    {
        "PermitCriteria": {
            "PermitTypeId": None, "PermitWorkclassId": None, "PermitStatusId": None,
            "ProjectName": None, "IssueDateFrom": "2026-06-01T00:00:00.000Z",
            "IssueDateTo": "2026-07-14T00:00:00.000Z",
            "SearchModule": 2, "PageNumber": 1, "PageSize": 10,
            "SortBy": "IssuedDate", "SortAscending": False,
        },
        "SearchModule": 2,
    },
]


def _probe(name: str, base: str):
    print(f"\n{'='*70}\n=== {name}: {base}\n{'='*70}")
    client = httpx.Client(
        headers={"User-Agent": UA, "Accept": "application/json, text/html;q=0.9"},
        follow_redirects=True, timeout=30,
    )

    # 1. Load the SPA shell — collects cookies, confirms reachability
    try:
        r = client.get(f"{base}#/home")
        print(f"[home] HTTP {r.status_code}, {len(r.text)} chars, "
              f"cookies={list(client.cookies.keys())}")
        if r.status_code != 200:
            print(r.text[:400])
    except Exception as e:
        print(f"[home] FAILED: {e}")
        return

    # 2. Version/metadata endpoints often reveal API root + auth needs
    for path in ("api/energov/version", "api/version", "api/energov/settings/global"):
        try:
            r = client.get(f"{base}/{path}")
            print(f"[GET {path}] HTTP {r.status_code} :: {r.text[:300]}")
        except Exception as e:
            print(f"[GET {path}] FAILED: {e}")

    # 3. Anti-forgery token (some tenants require the header pair)
    xsrf = None
    for path in ("api/energov/security/antiforgerytoken",
                 "api/security/antiforgerytoken"):
        try:
            r = client.get(f"{base}/{path}")
            print(f"[GET {path}] HTTP {r.status_code} :: {r.text[:200]}")
            if r.status_code == 200:
                try:
                    xsrf = r.json().get("token") or r.json().get("Token")
                except Exception:
                    pass
        except Exception as e:
            print(f"[GET {path}] FAILED: {e}")

    # 4. Search API attempts
    headers = {"Content-Type": "application/json"}
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    for i, body in enumerate(SEARCH_BODIES):
        for path in ("api/energov/search/search", "api/search/search"):
            try:
                r = client.post(f"{base}/{path}", content=json.dumps(body), headers=headers)
                snippet = r.text[:500].replace("\n", " ")
                print(f"[POST {path} body#{i}] HTTP {r.status_code} :: {snippet}")
                if r.status_code == 200 and ("Result" in r.text or "EntityResults" in r.text):
                    print(">>> SUCCESS — anonymous search works with this payload <<<")
                    return
            except Exception as e:
                print(f"[POST {path} body#{i}] FAILED: {e}")

    client.close()


def _debug():
    logging.basicConfig(level=logging.INFO)
    for name, base in TENANTS.items():
        _probe(name, base)


if __name__ == "__main__":
    _debug()
