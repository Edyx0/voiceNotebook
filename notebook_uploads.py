"""Keep file uploads on the SDK's HTTP pipeline, without an upload browser."""


def configure_file_uploads(client):
    # Test adapters and the Android backend retain their own implementation.
    uploader = getattr(getattr(client, 'sources', None), '_uploader', None)
    if uploader is None:
        return
    # notebooklm-py 0.8.5 routes uploads by account email. Google accepts the
    # bytes but processing fails; its file picker uses the numeric account slot.
    # Keep the SDK's registration, streaming and uncertain-result handling.
    uploader._authuser_query = lambda: f'authuser={uploader._auth.authuser}'
    uploader._authuser_header = lambda: str(uploader._auth.authuser)
