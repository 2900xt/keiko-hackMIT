from huggingface_hub import snapshot_download
p = snapshot_download("ivangtorre/watkins-marine-mammal-full-cuts", repo_type="dataset",
                      local_dir="raw/watkins_full", max_workers=4)
print("DONE", p)
