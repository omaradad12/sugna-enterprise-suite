"""
Customer portal hub, section landings, and stub pages (enterprise SaaS navigation shell).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from tenant_portal.decorators import tenant_view
from tenant_portal.portal_sitemap import (
    PORTAL_SECTIONS,
    build_portal_sidebar_nav,
    get_page,
    get_section,
    href_for_page,
    href_for_section,
)


def _ctx(
    request: HttpRequest,
    *,
    current_section: str | None = None,
    current_page: str | None = None,
    page_title: str | None = None,
    page_description: str | None = None,
) -> dict:
    return {
        "portal_nav": build_portal_sidebar_nav(current_section, current_page),
        "portal_current_section": current_section,
        "portal_current_page": current_page,
        "portal_page_title": page_title,
        "portal_page_description": page_description,
        "portal_hub_url": reverse("tenant_portal:customer_portal_hub"),
    }


@tenant_view()
def customer_portal_hub_view(request: HttpRequest) -> HttpResponse:
    sections = []
    for sec in PORTAL_SECTIONS:
        sections.append(
            {
                "section": sec,
                "section_url": href_for_section(sec.id),
                "preview_pages": sec.pages[:4],
            }
        )
    ctx = _ctx(request, current_section=None, current_page=None)
    ctx["portal_sections_grid"] = sections
    ctx["portal_all_sections"] = PORTAL_SECTIONS
    return render(request, "tenant_portal/portal/hub.html", ctx)


@tenant_view()
def customer_portal_section_view(request: HttpRequest, section: str) -> HttpResponse:
    sec = get_section(section)
    if not sec:
        from django.http import Http404

        raise Http404("Unknown portal section")
    pages_out = []
    for p in sec.pages:
        pages_out.append(
            {
                "page": p,
                "href": href_for_page(sec.id, p),
                "is_redirect": bool(p.redirect_url_name),
            }
        )
    ctx = _ctx(request, current_section=sec.id, current_page=None)
    ctx["portal_section"] = sec
    ctx["portal_section_pages"] = pages_out
    ctx["portal_section_url"] = href_for_section(sec.id)
    return render(request, "tenant_portal/portal/section.html", ctx)


@tenant_view()
def customer_portal_page_view(request: HttpRequest, section: str, page: str) -> HttpResponse:
    sec = get_section(section)
    pdef = get_page(section, page) if sec else None
    if not sec or not pdef:
        from django.http import Http404

        raise Http404("Unknown portal page")
    if pdef.redirect_url_name:
        try:
            return redirect(reverse(pdef.redirect_url_name))
        except NoReverseMatch:
            pass
    ctx = _ctx(
        request,
        current_section=sec.id,
        current_page=pdef.id,
        page_title=pdef.label,
        page_description=pdef.description,
    )
    ctx["portal_section"] = sec
    ctx["portal_page"] = pdef
    ctx["portal_section_url"] = href_for_section(sec.id)
    return render(request, "tenant_portal/portal/page_stub.html", ctx)
