from __future__ import annotations

from django import forms
from django.db import IntegrityError
from django.utils.text import slugify

from mscrInventory.management.commands.import_products_csv import generate_auto_sku
from mscrInventory.models import (
    Category,
    ContainerType,
    Ingredient,
    IngredientType,
    Packaging,
    Product,
    RecipeModifier,
    RoastProfile,
    SizeLabel,
    SquareUnmappedItem,
)


class ProductForm(forms.ModelForm):
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.order_by("name"),
        required=False,
        widget=forms.SelectMultiple,
        label="Categories",
    )
    sku = forms.CharField(max_length=128, required=False, label="SKU")

    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "shopify_id",
            "square_id",
            "categories",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if field_name == "categories":
                field.widget = forms.SelectMultiple(attrs={"class": "form-select", "size": 6})
            else:
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (existing + " form-control").strip()
            field.widget.attrs.setdefault("autocomplete", "off")

            if self.is_bound and field_name in self.errors:
                css = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{css} is-invalid".strip()

        self.fields["sku"].required = False
        self.fields["shopify_id"].required = False
        self.fields["square_id"].required = False

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip()

        qs = Product.objects.all()
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if not sku:
            base_name = self.cleaned_data.get("name") or getattr(self.instance, "name", "")
            base_name = (base_name or "product").strip()

            while True:
                sku = generate_auto_sku(base_name)
                if not qs.filter(sku__iexact=sku).exists():
                    break
        else:
            if qs.filter(sku__iexact=sku).exists():
                raise forms.ValidationError("A product with this SKU already exists.")

        return sku

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.name = (self.cleaned_data.get("name") or "").strip()
        instance.sku = (self.cleaned_data.get("sku") or "").strip()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class IngredientForm(forms.ModelForm):
    ROAST_TYPE_NAMES = {"coffee", "roast", "roasts"}
    PACKAGING_TYPE_NAMES = {"packaging"}

    class Meta:
        model = Ingredient
        fields = [
            "name",
            "type",
            "unit_type",
            "current_stock",
            "case_size",
            "reorder_point",
            "lead_time",
            "average_cost_per_unit",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} form-control".strip()
            widget.attrs.setdefault("autocomplete", "off")
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)

    @staticmethod
    def _requires_type(type_obj, valid_names: set[str]) -> bool:
        if not type_obj:
            return False
        normalized = (type_obj.name or "").strip().lower()
        return normalized in valid_names

    @classmethod
    def requires_roast_fields(cls, type_obj) -> bool:
        return cls._requires_type(type_obj, cls.ROAST_TYPE_NAMES)

    @classmethod
    def requires_packaging_fields(cls, type_obj) -> bool:
        return cls._requires_type(type_obj, cls.PACKAGING_TYPE_NAMES)


class RoastProfileForm(forms.Form):
    bag_size = forms.ChoiceField(choices=RoastProfile.BAG_SIZES, label="Bag Size")
    grind = forms.ChoiceField(choices=RoastProfile.GRINDS, label="Grind")

    def __init__(self, *args, ingredient: Ingredient | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        profile = None
        if ingredient:
            try:
                profile = ingredient.roastprofile
            except RoastProfile.DoesNotExist:
                profile = None

        if not self.is_bound:
            self.initial.setdefault(
                "bag_size",
                profile.bag_size if profile else RoastProfile._meta.get_field("bag_size").get_default(),
            )
            self.initial.setdefault(
                "grind",
                profile.grind if profile else RoastProfile._meta.get_field("grind").get_default(),
            )

        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-select".strip()


class PackagingForm(forms.Form):
    container = forms.ModelChoiceField(
        queryset=ContainerType.objects.order_by("name"),
        required=False,
        label="Container",
    )
    temp = forms.ChoiceField(choices=Packaging.Temps, label="Temperature", required=False)
    size_labels = forms.ModelMultipleChoiceField(
        queryset=SizeLabel.objects.order_by("label"),
        required=False,
        label="Size Labels",
    )
    multiplier = forms.FloatField(required=False, label="Multiplier")
    expands_to = forms.ModelMultipleChoiceField(
        queryset=Ingredient.objects.filter(type__name__iexact="packaging").order_by("name"),
        required=False,
        label="Expands To",
    )

    def __init__(self, *args, ingredient: Ingredient | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        packaging = None
        if ingredient:
            try:
                packaging = ingredient.packaging
            except Packaging.DoesNotExist:
                packaging = None
            expands_field = self.fields.get("expands_to")
            if expands_field is not None:
                expands_field.queryset = expands_field.queryset.exclude(pk=ingredient.pk)

        if not self.is_bound and packaging:
            self.initial.setdefault("container", packaging.container_id)
            self.initial.setdefault("temp", packaging.temp)
            self.initial.setdefault("multiplier", packaging.multiplier)
            self.initial.setdefault(
                "size_labels",
                list(packaging.size_labels.values_list("pk", flat=True)),
            )
            self.initial.setdefault(
                "expands_to",
                list(packaging.expands_to.values_list("pk", flat=True)),
            )

        for field_name, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(field, forms.ModelMultipleChoiceField):
                widget.attrs["class"] = f"{existing} form-select".strip()
                widget.attrs.setdefault("multiple", True)
                widget.attrs.setdefault("size", 4)
            elif isinstance(field, forms.ModelChoiceField) or isinstance(field, forms.ChoiceField):
                widget.attrs["class"] = f"{existing} form-select".strip()
            else:
                widget.attrs["class"] = f"{existing} form-control".strip()


class LinkUnmappedItemForm(forms.Form):
    """Resolve an unmapped item by linking to an existing record."""

    filter_type = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, item: SquareUnmappedItem, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)

        field_kwargs = {"required": True}
        if getattr(item, "is_known_recipe", False):
            field_kwargs["queryset"] = Product.objects.order_by("name")
            field_kwargs["label"] = "Product"
        elif item.item_type == "product":
            field_kwargs["queryset"] = Product.objects.order_by("name")
            field_kwargs["label"] = "Product"
        elif item.item_type == "ingredient":
            field_kwargs["queryset"] = Ingredient.objects.order_by("name")
            field_kwargs["label"] = "Ingredient"
        else:
            field_kwargs["queryset"] = RecipeModifier.objects.order_by("name")
            field_kwargs["label"] = "Modifier"

        self.fields["target"] = forms.ModelChoiceField(**field_kwargs)
        css_class = "form-select" if isinstance(self.fields["target"].widget, forms.Select) else "form-control"
        self.fields["target"].widget.attrs.setdefault("class", css_class)

    def save(self, user=None) -> SquareUnmappedItem:
        target = self.cleaned_data["target"]
        if getattr(self.item, "is_known_recipe", False):
            if self.item.item_type != "product":
                self.item.item_type = "product"
                self.item.save(update_fields=["item_type"])
            self.item.mark_resolved(user=user, product=target)
        elif self.item.item_type == "product":
            self.item.mark_resolved(user=user, product=target)
        elif self.item.item_type == "ingredient":
            self.item.mark_resolved(user=user, ingredient=target)
        else:
            self.item.mark_resolved(user=user, modifier=target)
        return self.item


class CreateFromUnmappedItemForm(forms.Form):
    """Create a new record directly from an unmapped entry."""

    filter_type = forms.CharField(required=False, widget=forms.HiddenInput())
    name = forms.CharField(max_length=255, label="Name")

    # Product specific
    sku = forms.CharField(max_length=128, required=False, label="SKU")

    # Ingredient specific
    ingredient_type = forms.ModelChoiceField(
        queryset=IngredientType.objects.order_by("name"),
        required=False,
        label="Ingredient Type",
    )

    # Modifier specific
    modifier_ingredient = forms.ModelChoiceField(
        queryset=Ingredient.objects.order_by("name"),
        required=False,
        label="Base Ingredient",
    )
    modifier_type = forms.ModelChoiceField(
        queryset=IngredientType.objects.order_by("name"),
        required=False,
        label="Applies To Type",
    )
    behavior = forms.ChoiceField(
        choices=RecipeModifier.ModifierBehavior.choices,
        required=False,
        label="Behavior",
    )
    base_quantity = forms.DecimalField(initial=1, min_value=0, required=False)
    unit = forms.CharField(max_length=20, required=False, initial="ea")

    def __init__(self, *args, item: SquareUnmappedItem, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)

        self.is_known_recipe = bool(getattr(item, "is_known_recipe", False))
        self.effective_item_type = "product" if self.is_known_recipe else item.item_type

        # Initialise defaults from the unmapped item
        self.fields["name"].initial = item.price_point_name or item.item_name
        self.fields["filter_type"].initial = kwargs.get("initial", {}).get("filter_type")

        if self.effective_item_type == "product":
            self.fields["sku"].required = False
            self.fields["sku"].initial = self._generate_default_sku(item)
        else:
            self.fields.pop("sku")

        if self.effective_item_type == "ingredient":
            self.fields["ingredient_type"].required = False
        else:
            self.fields.pop("ingredient_type")

        if self.effective_item_type == "modifier":
            self.fields["modifier_ingredient"].required = True
            self.fields["behavior"].required = True
            self.fields["behavior"].initial = RecipeModifier.ModifierBehavior.ADD
            self.fields["base_quantity"].required = True
            self.fields["unit"].required = True
        else:
            for field in (
                "modifier_ingredient",
                "modifier_type",
                "behavior",
                "base_quantity",
                "unit",
            ):
                self.fields.pop(field)

        for name, field in self.fields.items():
            if name == "filter_type":
                continue
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def save(self, user=None) -> SquareUnmappedItem:
        name = self.cleaned_data["name"].strip()

        item_type = "product" if getattr(self.item, "is_known_recipe", False) else self.item.item_type

        if item_type == "product":
            sku = self.cleaned_data.get("sku") or self._generate_default_sku(self.item, fallback=name)
            try:
                product = Product.objects.create(name=name, sku=sku)
            except IntegrityError as exc:
                raise forms.ValidationError(
                    "A product with this name or SKU already exists. Use 'Link to Existing' instead."
                ) from exc
            if getattr(self.item, "is_known_recipe", False) and self.item.item_type != "product":
                self.item.item_type = "product"
                self.item.save(update_fields=["item_type"])
            self.item.mark_resolved(user=user, product=product)
        elif item_type == "ingredient":
            try:
                ingredient = Ingredient.objects.create(
                    name=name,
                    type=self.cleaned_data.get("ingredient_type"),
                )
            except IntegrityError as exc:
                raise forms.ValidationError(
                    "An ingredient with this name already exists. Use 'Link to Existing' instead."
                ) from exc
            self.item.mark_resolved(user=user, ingredient=ingredient)
        else:
            ingredient = self.cleaned_data["modifier_ingredient"]
            behavior = self.cleaned_data["behavior"]
            base_quantity = self.cleaned_data.get("base_quantity") or 1
            unit = self.cleaned_data.get("unit") or "ea"
            modifier_type = ingredient.type or self.cleaned_data.get("modifier_type")
            if modifier_type is None:
                raise forms.ValidationError(
                    "Select an ingredient with a type or specify an 'Applies To Type'."
                )
            try:
                modifier = RecipeModifier.objects.create(
                    name=name,
                    ingredient=ingredient,
                    ingredient_type=modifier_type,
                    behavior=behavior,
                    quantity_factor=1,
                    base_quantity=base_quantity,
                    unit=unit,
                )
            except IntegrityError as exc:
                raise forms.ValidationError(
                    "A modifier with this name already exists. Use 'Link to Existing' instead."
                ) from exc
            self.item.mark_resolved(user=user, modifier=modifier)
        return self.item

    @staticmethod
    def _generate_default_sku(item: SquareUnmappedItem, fallback: str | None = None) -> str:
        base = fallback or item.price_point_name or item.item_name or "square-item"
        slug = slugify(base) or "square-item"
        candidate = slug[:12].upper()
        if not candidate:
            candidate = "SQUARE"

        counter = 1
        while Product.objects.filter(sku=candidate).exists():
            counter += 1
            candidate = f"{slug[:10].upper()}-{counter}" if slug else f"SQUARE-{counter}"
        return candidate
