# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from idx_normalizator import normalize_url_key
from slugify import slugify


def generate_url_key(name: str, idx: str | None = None, append_idx=False, max_length: int = 200):
    slug = slugify(name)
    if idx and append_idx:
        url_key = "%s-%s" % (slug[: max_length - len(idx)], str(idx))
    else:
        url_key = slug[:max_length]

    return normalize_url_key(url_key)
