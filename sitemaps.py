from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from catalog.models import Product


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.filter(status=Product.PUBLISHED)

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("storefront:product", args=[obj.slug])


class StaticSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return ["storefront:home", "storefront:shop", "storefront:about",
                "storefront:support"]

    def location(self, item):
        return reverse(item)
