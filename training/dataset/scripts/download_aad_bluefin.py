"""Download the AAD AcousticTrends_BlueFinLibrary via its S3-compatible endpoint (credentials from AADC email; expire 2026-10-04).
Usage: AAD_CREDS=/path/creds.json python3 scripts/download_aad_bluefin.py"""
import boto3, json, certifi, os, pathlib, concurrent.futures as cf, sys, time
c = json.load(open(os.environ["AAD_CREDS"]))
root = pathlib.Path(__file__).resolve().parent.parent / "raw" / "aad_bluefin"
s3 = boto3.client("s3", endpoint_url=c["endpoint"], aws_access_key_id=c["access"], aws_secret_access_key=c["secret"], verify=certifi.where())
keys, token = [], None
while True:
    kw = dict(Bucket=c["bucket"], Prefix=c["prefix"], MaxKeys=1000); kw.update(ContinuationToken=token) if token else None
    r = s3.list_objects_v2(**kw); keys += [(o["Key"], o["Size"]) for o in r.get("Contents", [])]
    token = r.get("NextContinuationToken")
    if not token: break
print("objects", len(keys), round(sum(s for _, s in keys)/1e9, 2), "GB", flush=True)
def get(k, size):
    dst = root / k[len(c["prefix"]):]
    if dst.exists() and dst.stat().st_size == size: return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try: s3.download_file(c["bucket"], k, str(dst)); return size
        except Exception as e:
            if attempt == 3: print("FAIL", k, e, flush=True); return -1
            time.sleep(2 * (attempt + 1))
done = 0; t0 = time.time()
with cf.ThreadPoolExecutor(32) as ex:
    for i, n in enumerate(ex.map(lambda ks: get(*ks), keys), 1):
        if n > 0: done += n
        if i % 500 == 0: print(f"{i}/{len(keys)} files, {done/1e9:.2f} GB new, {time.time()-t0:.0f}s", flush=True)
print("AAD_DONE", done/1e9, "GB new", flush=True)
