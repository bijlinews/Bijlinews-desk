"""Blogger API v3: create a post, keep an English permalink, show a Hindi title."""
import requests

from . import config

BASE = "https://www.googleapis.com/blogger/v3/blogs/{blog}/posts"


def _token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "refresh_token": config.GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


class Blogger:
    def __init__(self):
        self.h = {"Authorization": f"Bearer {_token()}"}
        self.base = BASE.format(blog=config.BLOG_ID)

    def create(self, slug_title, hindi_title, html, labels, publish):
        """Blogger builds the URL from the title at publish time, so we publish with the
        English slug as the title and then rename the post to its Hindi title (URL stays)."""
        r = requests.post(self.base, headers=self.h, params={"isDraft": "true"},
                          json={"title": slug_title, "content": html, "labels": labels}, timeout=60)
        r.raise_for_status()
        post = r.json()
        if publish:
            r = requests.post(f"{self.base}/{post['id']}/publish", headers=self.h, timeout=60)
            r.raise_for_status()
            post = r.json()
        r = requests.patch(f"{self.base}/{post['id']}", headers=self.h,
                           json={"title": hindi_title}, timeout=60)
        r.raise_for_status()
        post = r.json()
        post["edit_url"] = f"https://www.blogger.com/blog/post/edit/{config.BLOG_ID}/{post['id']}"
        return post

    def recent_titles(self, n=40):
        r = requests.get(self.base, headers=self.h,
                         params={"maxResults": n, "fetchBodies": "false", "status": ["live", "draft"]}, timeout=60)
        r.raise_for_status()
        return [p.get("title", "") for p in r.json().get("items", [])]
