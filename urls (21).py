"""Root URL configuration for Campus Connect."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path

from storefront.sitemaps import ProductSitemap, StaticSitemap

admin.site.site_header = "Campus Connect Administration"
admin.site.site_title = "Campus Connect Admin"
admin.site.index_title = "Store administration — Powered by LAVIDA"

sitemaps = {"products": ProductSitemap, "static": StaticSitemap}


def robots(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /backoffice/",
        "Disallow: /accounts/",
        "Disallow: /orders/",
        "Allow: /",
        "Sitemap: " + request.build_absolute_uri("/sitemap.xml"),
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("backoffice/", include("backoffice.urls")),
    path("accounts/", include("accounts.urls")),
    path("orders/", include("orders.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps},
         name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", robots),
    path("", include("storefront.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")

handler404 = "storefront.errors.handler404"
handler500 = "storefront.errors.handler500"
handler403 = "storefront.errors.handler403"
