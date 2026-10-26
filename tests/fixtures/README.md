# Provider fixtures

These JSON files are **synthetic** fixtures shaped like Amazon Music and
lucidadl payloads. They pin the parser's expected structure but are not
captured live responses. Live response capture remains a manual verification
step because provider pages are unstable and may contain account/session data.

- `amazon_search.json`: `showSearch` widget shape.
- `amazon_artist.json`: `showCatalogArtist` nested item shape.
- `lucida_album.json`: `fetch_page_data().info` album shape.

Do not add cookies, clearance values, account data, or machine-specific paths
to these fixtures.
