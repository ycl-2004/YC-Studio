"""HTTP dependencies shared by product API routes.

Authentication is deliberately deferred to Stage 4.  Until then, the gateway or
local client supplies the authenticated principal as ``X-User-ID``; keeping that
translation in one dependency means the knowledge-base routes never trust a
collection owner supplied in a request body.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Header


async def get_current_user_id(
    x_user_id: Annotated[UUID, Header(alias="X-User-ID")],
) -> UUID:
    """Return the request principal selected by the current identity boundary.

    Stage 4 must replace this header source with verified JWT/session identity;
    route and service signatures intentionally remain unchanged.
    """

    return x_user_id
