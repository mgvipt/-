from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0006_supplierproductmap_qty_factor"),
        ("warehouse", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssemblyRecipe",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("supplier_key", models.CharField(blank=True, db_index=True, default="", max_length=120)),
                ("signature", models.CharField(db_index=True, max_length=240)),
                ("default_qty", models.DecimalField(decimal_places=3, default=1, max_digits=12)),
                ("components", models.JSONField(blank=True, default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("target_product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assembly_recipes", to="warehouse.product")),
            ],
        ),
        migrations.AddIndex(
            model_name="assemblyrecipe",
            index=models.Index(fields=["supplier_key", "signature"], name="integration_supplie_asm_idx"),
        ),
    ]
