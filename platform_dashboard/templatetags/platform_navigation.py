from django import template

from platform_dashboard.navigation import build_sidebar_menu

register = template.Library()


@register.inclusion_tag("platform_dashboard/includes/platform_sidebar.html", takes_context=True)
def render_platform_sidebar(context):
    request = context["request"]
    return {
        "request": request,
        "platform_menu": build_sidebar_menu(request),
    }
