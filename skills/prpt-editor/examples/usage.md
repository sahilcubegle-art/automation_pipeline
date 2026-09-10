# Usage

```powershell
python skills/prpt-editor/prpt_editor.py inspect IncomeStatement_GST.prpt
python skills/prpt-editor/prpt_editor.py find IncomeStatement_GST.prpt tax --limit 20
python skills/prpt-editor/prpt_editor.py find IncomeStatement_GST.prpt --expression 'SUM'
python skills/prpt-editor/prpt_editor.py add-parameter report.prpt --name VAT_RATE --type java.lang.Double --default 0.18 --label 'VAT rate'
python skills/prpt-editor/prpt_editor.py modify-expression report.prpt --target layout.xml#42 --expect '$F{income}' --expression '$F{income} * 1.18'
python skills/prpt-editor/prpt_editor.py validate report.prpt
```

The script emits compact JSON, so send only its relevant matching entries to the reasoning stage.
