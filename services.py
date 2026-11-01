"""Inventory service functions. All stock changes go through here so that
negative inventory is impossible and every movement is recorded.
"""
from django.db import transaction

from .models import InventoryMovement, Product


class InsufficientStock(Exception):
    pass


@transaction.atomic
def adjust_stock(product, delta, reason, user=None, note=""):
    """Apply a signed `delta` to a product's stock, recording a movement.

    Raises InsufficientStock if the result would be negative.
    """
    locked = Product.objects.select_for_update().get(pk=product.pk)
    new_qty = locked.stock_quantity + delta
    if new_qty < 0:
        raise InsufficientStock(
            f"Cannot reduce {locked.sku} below zero "
            f"(have {locked.stock_quantity}, requested {delta})."
        )
    locked.stock_quantity = new_qty
    # Auto out-of-stock / republish bookkeeping.
    if new_qty == 0 and locked.status == Product.PUBLISHED:
        locked.status = Product.OUT_OF_STOCK
    elif new_qty > 0 and locked.status == Product.OUT_OF_STOCK:
        locked.status = Product.PUBLISHED
    locked.save(update_fields=["stock_quantity", "status", "updated_at"])
    InventoryMovement.objects.create(
        product=locked,
        reason=reason,
        quantity_delta=delta,
        resulting_quantity=new_qty,
        note=note,
        created_by=user,
    )
    return locked


def set_stock(product, target_qty, user=None, note=""):
    """Correct stock to an absolute target quantity."""
    delta = target_qty - product.stock_quantity
    return adjust_stock(
        product, delta, InventoryMovement.CORRECTION, user=user,
        note=note or f"Corrected to {target_qty}",
    )
