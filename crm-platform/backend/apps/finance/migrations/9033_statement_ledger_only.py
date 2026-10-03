from django.db import migrations,models
import django.db.models.deletion
class Migration(migrations.Migration):
 dependencies=[('finance','9032_loan_account_loan_pull_from')]
 operations=[migrations.CreateModel(name='StatementRow',fields=[
  ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
  ('key',models.CharField(max_length=64,unique=True)),('file_hash',models.CharField(max_length=64,db_index=True)),
  ('bank_id',models.CharField(max_length=160,blank=True)),('bank_leg',models.CharField(max_length=160,blank=True)),
  ('source_data',models.JSONField(default=dict,blank=True)),('created_at',models.DateTimeField(auto_now_add=True)),
  ('transaction',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='statement_row',to='finance.transaction'))])]
