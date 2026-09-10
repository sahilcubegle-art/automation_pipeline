# How Claude Code Works with Pentaho .prpt Files

## Overview
This document explains Claude Code's approach, tools, and workflow when modifying Pentaho Report files (.prpt) in a repository with multiple reports.

---

## The Challenge

**Scenario:** You have a repository with 10+ .prpt files and receive a requirement like:
> "Add 18% GST calculation to all income reports"

**Problem:** You don't know which specific files need changes or how they're structured internally.

---

## Claude Code's Approach

### Phase 1: Discovery & Understanding

#### 1.1 Repository Exploration
**Tools Used:**
- `Glob` - Find all .prpt files in the repository
- `PowerShell` or `Bash` - List and inspect files

**What Claude Does:**
```powershell
# Find all .prpt files
Get-ChildItem -Path "D:\vinnow" -Filter "*.prpt" -Recurse
```

**Output:** List of all Pentaho report files with their locations and sizes.

#### 1.2 Understanding .prpt Structure
**Key Insight:** Claude knows that .prpt files are ZIP archives containing XML files.

**Tools Used:**
- `PowerShell Expand-Archive` - Extract ZIP contents
- `Read` tool - Examine XML files

**What Claude Does:**
```powershell
# Extract a .prpt file to examine its structure
Expand-Archive -Path "Income Statement.prpt" -DestinationPath "temp_extract"
```

**Files Claude Examines:**
- `layout.xml` - Report visual structure and formulas
- `datadefinition.xml` - Data queries and sources
- `dataschema.xml` - Data field definitions
- `META-INF/manifest.xml` - File manifest
- `mimetype` - Archive type identifier

#### 1.3 Content Analysis
**Tools Used:**
- `Read` tool - Read XML file contents
- `Grep` - Search for specific patterns across files

**What Claude Searches For:**
```powershell
# Search for "Net Income" across all extracted layouts
Get-ChildItem -Recurse -Filter "layout.xml" | Select-String -Pattern "Net Income"
```

**Key Patterns:**
- Report identifiers (Net Income, Total Assets, Revenue, etc.)
- Formula expressions `[FieldName]`, `$([Field] * value)`
- Element structures `<message>`, `<number-field>`, `<label>`
- Position coordinates `x`, `y`, `min-width`, `min-height`

---

### Phase 2: Requirement Mapping

#### 2.1 Requirement Analysis
**Cognitive Process:**
1. Parse user requirement: "Add 18% GST"
2. Identify affected reports: Income Statement (has Net Income)
3. Determine calculation logic: `Net Income * 0.18 = GST Amount`
4. Plan display structure: Show before GST, GST amount, after GST

#### 2.2 File Identification
**Decision Logic:**
```
IF layout.xml contains "Net Income" OR "Profit"
   THEN this is an Income Statement → needs GST
   
IF layout.xml contains "Total Assets" OR "Liabilities"
   THEN this is a Balance Sheet → no GST needed
   
IF layout.xml contains "Cash Flow"
   THEN this is a Cash Flow Statement → no GST needed
```

**Tools Used:**
- Pattern matching in XML content
- Semantic understanding of accounting terms

---

### Phase 3: XML Modification

#### 3.1 Locate Modification Point
**What Claude Looks For:**
- The element containing "Net Income" label
- Its position (x, y coordinates)
- The formula field associated with it
- The parent container (usually `<report-footer>`)

**Tools Used:**
- `Read` with `offset` and `limit` - Read specific line ranges
- XML structure analysis

**Example:**
```xml
<!-- Found at line 748 -->
<message core:null-value="">
  <core:value>Net Income</core:value>
</message>
```

#### 3.2 Formula Understanding
**Claude Identifies:**
- Field reference: `[Summary_AmountExpression]`
- Formula syntax: `$ $([Field] * multiplier, format, pattern)`
- Formatting: `number, #,###` for currency display

#### 3.3 XML Element Creation
**Tools Used:**
- String manipulation in PowerShell/Python
- XML structure knowledge from Pentaho documentation

**What Claude Generates:**
```xml
<!-- GST Label -->
<message core:null-value="">
  <style:element-style>
    <style:common-styles alignment="left" vertical-alignment="middle"/>
    <style:spatial-styles x="0" y="20" min-width="432" min-height="14"/>
  </style:element-style>
  <core:value>GST @ 18%</core:value>
</message>

<!-- GST Calculation -->
<message core:null-value="">
  <style:element-style>
    <style:common-styles alignment="right" vertical-alignment="middle"/>
    <style:spatial-styles x="432" y="20" min-width="108" min-height="14"/>
  </style:element-style>
  <core:value>$ $([Summary_AmountExpression] * 0.18, number, #,###)</core:value>
</message>
```

**Key Decisions:**
- `y="20"` - Position below previous element (Net Income was at y="6")
- `x="432"` - Right-aligned position for amounts
- `alignment="right"` - Standard for numbers
- Formula: `[Summary_AmountExpression] * 0.18` - 18% calculation

#### 3.4 File Modification
**Tools Used:**
- `Edit` tool - Replace specific XML sections
- `Write` tool - Create modified files

**Process:**
```powershell
# Read original content
$content = Get-Content "temp_extract\layout.xml" -Raw

# Find insertion point (using regex or line numbers)
$insertionPoint = $content.IndexOf('</message>', $netIncomePosition)

# Insert new XML elements
$newContent = $content.Insert($insertionPoint, $gstElements)

# Write back
Set-Content "temp_extract\layout.xml" -Value $newContent
```

---

### Phase 4: ZIP Repackaging

#### 4.1 Understanding Pentaho ZIP Requirements
**Critical Knowledge:**
- `mimetype` file must be **uncompressed**
- `mimetype` must be the **first file** in the archive
- All other files can be compressed with standard compression

**Why This Matters:**
Standard PowerShell `Compress-Archive` compresses everything, which breaks Pentaho compatibility.

#### 4.2 Custom ZIP Creation
**Tools Used:**
- `.NET System.IO.Compression.ZipFile` class
- PowerShell scripting

**Process:**
```powershell
# Load .NET ZIP library
Add-Type -AssemblyName System.IO.Compression.FileSystem

# Create new ZIP
$zip = [System.IO.Compression.ZipFile]::Open(
    "IncomeStatement_GST.prpt", 
    'Create'
)

# Add mimetype UNCOMPRESSED (critical!)
$mimeEntry = $zip.CreateEntry(
    'mimetype', 
    [System.IO.Compression.CompressionLevel]::NoCompression
)
$writer = New-Object System.IO.StreamWriter($mimeEntry.Open())
$writer.Write('application/vnd.pentaho.reporting.classic')
$writer.Close()

# Add all other files with compression
Get-ChildItem -Recurse | ForEach-Object {
    if ($_.Name -ne 'mimetype') {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip,
            $_.FullName,
            $relativePath,
            [System.IO.Compression.CompressionLevel]::Optimal
        )
    }
}

$zip.Dispose()
```

---

### Phase 5: Validation & Error Handling

#### 5.1 Common Errors Claude Encounters

**Error 1: Invalid XML Element**
```
ResourceCreationException: Invalid element 'resource-field'
```

**Root Cause:** Used non-existent XML element type

**Claude's Fix:** 
- Research Pentaho XML schema
- Use correct element `<message>` with formula in `<core:value>`

**Error 2: ZIP Structure Invalid**
```
ResourceCreationException: Unable to parse document
```

**Root Cause:** `mimetype` file was compressed

**Claude's Fix:**
- Abandon `Compress-Archive`
- Implement custom ZIP with .NET classes
- Ensure `mimetype` is stored uncompressed

#### 5.2 Verification Steps
**Tools Used:**
- File size comparison
- ZIP integrity check
- Manual testing recommendation

**What Claude Checks:**
```powershell
# Verify file was created
Test-Path "IncomeStatement_GST.prpt"

# Check file size (should be similar to original)
(Get-Item "IncomeStatement_GST.prpt").Length

# Verify ZIP structure
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead("IncomeStatement_GST.prpt")
$zip.Entries | Select-Object Name, CompressedLength, Length
```

---

## Tool Arsenal

### Core Tools Claude Uses

| Tool | Purpose | Use Case |
|------|---------|----------|
| **Glob** | Pattern-based file search | Find all .prpt files in repo |
| **Grep** | Content search across files | Search for "Net Income" in XMLs |
| **Read** | Read file contents | Examine layout.xml structure |
| **Edit** | Modify existing files | Update XML elements |
| **Write** | Create new files | Write modified layout.xml |
| **PowerShell** | Execute system commands | Extract ZIP, create archives |
| **Bash** | Alternative shell (if available) | POSIX-compliant operations |

### Specialized Capabilities

| Capability | How It Works |
|------------|--------------|
| **XML Parsing** | Understands XML structure without external libraries |
| **Pattern Recognition** | Identifies report types by content patterns |
| **Formula Analysis** | Parses Pentaho formula syntax `$([Field] * value)` |
| **Spatial Reasoning** | Calculates element positions (x, y coordinates) |
| **Archive Manipulation** | Custom ZIP creation with compression control |

---

## Workflow for Multiple Files

### Scenario: 10 Reports, Need to Add GST to All Income Statements

**Step 1: Bulk Discovery**
```powershell
# Extract all reports
Get-ChildItem "*.prpt" | ForEach-Object {
    Expand-Archive $_ -Dest "analysis\$($_.BaseName)"
}
```

**Step 2: Classification**
```powershell
# Classify each report
$reports = @()
Get-ChildItem "analysis\*\layout.xml" | ForEach-Object {
    $content = Get-Content $_ -Raw
    $type = "Unknown"
    
    if ($content -match "Net Income|Profit") { $type = "Income Statement" }
    if ($content -match "Total Assets") { $type = "Balance Sheet" }
    if ($content -match "Cash Flow") { $type = "Cash Flow" }
    
    $reports += [PSCustomObject]@{
        File = $_.Directory.Parent.Name
        Type = $type
        NeedsGST = ($type -eq "Income Statement")
    }
}

# Show results
$reports | Format-Table
```

**Output Example:**
```
File                    Type              NeedsGST
----                    ----              --------
Income Statement        Income Statement  True
Balance Sheet           Balance Sheet     False
Quarterly Report        Income Statement  True
Cash Flow 2024          Cash Flow         False
...
```

**Step 3: Batch Processing**
```powershell
# Process only Income Statements
$reports | Where-Object { $_.NeedsGST } | ForEach-Object {
    # Apply GST modification logic
    # 1. Read layout.xml
    # 2. Find Net Income element
    # 3. Insert GST calculation
    # 4. Repackage as .prpt
}
```

---

## Decision Tree

```
User Request: "Add 18% GST"
    ↓
┌─────────────────────────────┐
│ Search for .prpt files      │ ← Glob tool
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Extract each .prpt          │ ← PowerShell Expand-Archive
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Read layout.xml             │ ← Read tool
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Does it contain             │
│ "Net Income"?               │ ← Pattern matching
└─────────────────────────────┘
    ↓           ↓
   YES         NO → Skip this file
    ↓
┌─────────────────────────────┐
│ Find Net Income element     │ ← XML parsing
│ position and formula        │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Generate GST XML elements   │ ← Knowledge of Pentaho XML
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Insert into layout.xml      │ ← Edit tool
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Repackage as .prpt          │ ← .NET ZipFile with
│ (mimetype uncompressed!)    │   custom compression
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Verify file integrity       │ ← Test-Path, size check
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ Provide modified file       │
└─────────────────────────────┘
```

---

## Knowledge Sources

### How Claude Knows What to Do

1. **Training Data:**
   - Pentaho Report Designer documentation
   - XML structure patterns
   - Common accounting report formats

2. **In-Context Learning:**
   - Reads existing .prpt files to understand structure
   - Analyzes error messages to debug issues
   - Adapts approach based on what works

3. **Tool Documentation:**
   - PowerShell cmdlet syntax
   - .NET framework classes
   - ZIP file specifications

4. **Reasoning:**
   - "Net Income appears in Income Statements"
   - "GST is a tax applied to income"
   - "Calculations go in `<core:value>` with formula syntax"

---

## Example: Complete Workflow

### User Request
> "Add 18% GST to Income Statement.prpt"

### Claude's Internal Process

**1. Understand File Format**
```
Thought: .prpt is Pentaho Report, likely a ZIP archive
Action: Extract to examine structure
Tool: PowerShell Expand-Archive
```

**2. Locate Relevant Content**
```
Thought: Need to find where "Net Income" is displayed
Action: Read layout.xml and search for "Net Income"
Tool: Read + pattern matching
Result: Found at line 748 with formula [Summary_AmountExpression]
```

**3. Plan Modification**
```
Thought: Need to add:
  - "GST @ 18%" label
  - Calculation: [Summary_AmountExpression] * 0.18
  - "Net Income (After GST)": [Summary_AmountExpression] * 1.18
  
Position: Below current Net Income (y + 14 for each line)
Alignment: Left for labels, Right for amounts
```

**4. Generate XML**
```
Thought: Pentaho uses <message> elements with <core:value>
Action: Construct proper XML with styling
Tool: String manipulation
```

**5. Apply Changes**
```
Thought: Insert after existing Net Income element
Action: Edit layout.xml at specific line
Tool: Edit tool with exact string replacement
```

**6. Repackage**
```
Thought: Must create valid .prpt ZIP
Critical: mimetype must be uncompressed
Action: Use .NET ZipFile class with custom compression
Tool: PowerShell with .NET System.IO.Compression
```

**7. Verify**
```
Thought: File should be similar size to original
Action: Check file exists and is valid ZIP
Tool: Test-Path, Get-Item
```

---

## Limitations & Challenges

### What Claude Can Do
✅ Extract and analyze .prpt structure  
✅ Search for specific patterns in XML  
✅ Modify XML content programmatically  
✅ Create proper .prpt ZIP archives  
✅ Handle multiple files systematically  
✅ Debug and fix errors iteratively  

### What Claude Cannot Do
❌ Open Pentaho Report Designer GUI  
❌ Visually preview the report  
❌ Test report against live database  
❌ Auto-detect all formula dependencies  
❌ Guarantee visual layout perfection  

### Requires User Input
⚠️ Confirmation of which reports need changes  
⚠️ Database connection for testing  
⚠️ Pentaho Report Designer for final verification  
⚠️ Business logic clarification (e.g., "Apply GST to gross or net?")  

---

## Best Practices

### For Users Working with Claude on .prpt Files

1. **Provide Context:**
   ```
   Good: "Add 18% GST to all Income Statement reports"
   Better: "Add 18% GST calculation below Net Income in Income Statement.prpt, 
            showing: Net Income (Before GST), GST @ 18%, Net Income (After GST)"
   ```

2. **Clarify Scope:**
   - Specify which reports need changes
   - Provide example of desired output
   - Mention any formatting preferences

3. **Share Errors:**
   - If a modified .prpt fails to open, share the exact error message
   - Pentaho error messages contain valuable diagnostic information

4. **Test Iteratively:**
   - Test one report first
   - Verify in Pentaho Report Designer
   - Then apply to remaining reports

---

## Technical Deep Dive

### Why Standard ZIP Tools Don't Work

**Problem:**
```powershell
Compress-Archive -Path "temp_extract\*" -Dest "report.prpt"
# This FAILS in Pentaho!
```

**Reason:**
Pentaho Report Engine expects:
1. First entry must be `mimetype`
2. `mimetype` must have **zero compression**
3. Content: `application/vnd.pentaho.reporting.classic`

**Why It Matters:**
Pentaho uses `mimetype` to quickly identify file type without parsing the entire archive. Compressed `mimetype` breaks this fast identification.

**Solution:**
```powershell
# Manual ZIP creation with compression control
$zip = [System.IO.Compression.ZipFile]::Open($path, 'Create')
$entry = $zip.CreateEntry('mimetype', [System.IO.Compression.CompressionLevel]::NoCompression)
# ... write content ...
```

### XML Element Positioning

**Pentaho Layout Coordinate System:**
- Origin (0,0) is top-left
- Units are in points (1/72 inch)
- Elements positioned absolutely with x, y, width, height

**Example Calculation:**
```
Existing Net Income: y="6", height="14"
Next element starts: y = 6 + 14 + buffer
                    y = 20 (with some spacing)
```

**Claude's Spatial Reasoning:**
```
IF previous_element.y = 6 AND previous_element.height = 14
THEN new_element.y = previous_element.y + previous_element.height + spacing
     new_element.y = 6 + 14 + 0 = 20
```

---

## Summary

**Claude Code's approach to .prpt file modifications:**

1. **Discovery:** Find and extract all .prpt files
2. **Analysis:** Understand structure by reading XML files
3. **Classification:** Identify report types by content patterns
4. **Modification:** Apply changes to relevant XML elements
5. **Repackaging:** Create valid .prpt with proper ZIP structure
6. **Validation:** Verify file integrity and provide for testing

**Key Tools:** Glob, Read, Edit, PowerShell, .NET classes

**Key Knowledge:** XML structure, Pentaho formula syntax, ZIP format requirements

**Success Factor:** Iterative debugging based on error messages and structural understanding

---

## Created by Claude Code
*This document was automatically generated to explain Claude Code's internal workflow.*
