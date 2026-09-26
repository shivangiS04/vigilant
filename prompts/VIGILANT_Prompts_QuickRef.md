# VIGILANT PROMPTS: QUICK REFERENCE

Print this page & keep it on your desk.

---

## 🎯 WHICH PROMPT DO I NEED?

### "I need to explain an unusual Ring pattern to the user"
→ **PROMPT 1.1: Pattern Explanation**
- File: `backend/bedrock_integration/explanation_generator.py`
- Max explanation: 1-2 sentences
- Auto-adjusts tone based on salience score
- Copy-paste implementation included

---

### "I need to summarize multiple patterns from one day"
→ **PROMPT 1.2: Batch Explanation**
- Prevents alert fatigue
- Ranks patterns by importance
- Max 4 sentences total

---

### "I'm designing the MOTIF scoring algorithm"
→ **PROMPT 2.1: MOTIF Engine Design**
- 4 scoring layers (novelty, adaptation, temporal, competition)
- Weights: novelty=0.4, adaptation=0.3, temporal=0.2, competition=0.1
- Example calculation included
- Code template provided

---

### "My code is broken and I need help debugging"
→ **PROMPT 2.2: Ask Claude for MOTIF Implementation Help**
- Use this template when messaging Claude for coding help
- Includes context + constraints + what you need
- Copy-paste into Claude chat

---

### "I'm building the Ring API integration"
→ **PROMPT 3.1: Ring API Integration Help**
- Best approach for hackathon timeline
- Code skeleton for event streaming
- Error handling strategies
- Copy-paste template

---

### "I'm designing the database schema"
→ **PROMPT 3.2: Database Schema Design Help**
- PostgreSQL optimization tips
- Multi-camera support
- Pattern matching queries
- Copy-paste schema template

---

### "I'm building the React dashboard"
→ **PROMPT 3.3: Dashboard Component Help**
- Timeline component code
- Pattern card component
- Real-time update strategy
- Copy-paste React skeleton

---

### "I want +10% judging bonus (friction log)"
→ **PROMPT 4: Friction Log Template**
- Document problems you hit
- Show your workarounds
- Make suggestions to Amazon
- Up to 10 entries (get 10% bonus!)
- Copy-paste examples included

---

### "Final submission is coming up"
→ **PROMPT 5: Product Feedback**
- Required hackathon field
- Shows judges you understand the tools
- Describe what you built with Ring + Bedrock + AWS
- Copy-paste template (fill in your experience)

---

## 📋 PROMPT BY TIMELINE

| Days | Task | Prompt |
|------|------|--------|
| 1-2 | Environment setup | PROMPT 2.1 (context) |
| 3-4 | Ring integration | PROMPT 3.1 |
| 5-7 | MOTIF algorithm | PROMPT 2.1, 2.2 |
| 8-10 | Bedrock explanations | PROMPT 1.1 |
| 11-14 | MOTIF tuning | PROMPT 2.2 |
| 15-18 | Dashboard build | PROMPT 3.3 |
| 19-22 | Testing + friction log | PROMPT 4 |
| 23-27 | Final polish | PROMPT 5 (product feedback) |
| 28 | Submit! | Submit with PROMPT 4 + 5 |

---

## 🔑 KEY PROMPTS TO REMEMBER

### Most Important: PROMPT 1.1
**Why**: This is where the magic happens (Bedrock generates explanations)
**When**: Days 8-14 (after MOTIF is scoring patterns)
**Impact**: Makes product *useful* vs. just technical

### Most Valuable: PROMPT 4 (Friction Log)
**Why**: +10% judging bonus
**When**: Throughout (fill as you hit problems)
**Impact**: Easy points if you document challenges

### Most Strategic: PROMPT 5 (Product Feedback)
**Why**: Shows judges you understand Amazon's tools
**When**: Days 25-27 (final submission)
**Impact**: Differentiates your team

---

## 💡 PRO TIPS

✅ **Customize the context**: Fill in actual values (not placeholders)
- Instead of: `{location}` → write: `123 Main Street, Austin TX`
- Instead of: `{pattern_type}` → write: `rapid_return_side_door_entrance`

✅ **Use in Bedrock calls**: Copy the exact prompt into your boto3 calls
```python
# From PROMPT 1.1
prompt = f"""CONTEXT:
You are explaining a behavioral pattern...

HOME BASELINE:
- Location: {location}
...
"""

response = client.invoke_model(
    modelId=self.model_id,
    body=json.dumps({
        "messages": [{"role": "user", "content": prompt}]
    })
)
```

✅ **Share with team**: Post PROMPT 3.1, 3.2, 3.3 in team Slack
- Ring person uses PROMPT 3.1
- DB person uses PROMPT 3.2
- Frontend person uses PROMPT 3.3

✅ **Keep friction log as you go**
- Don't save it for the end
- Every problem you hit → add 1-2 lines to friction log
- Takes 2 minutes per entry, 10 entries = +10% on final score

---

## 📍 EXACT FILE LOCATIONS

Where to put each prompt:

```
vigilant-ring-ai/
├── backend/
│   ├── ring_integration/
│   │   └── api_client.py          ← Use PROMPT 3.1 code here
│   ├── motif_engine/
│   │   └── motif_core.py           ← Use PROMPT 2.1 code here
│   ├── bedrock_integration/
│   │   └── explanation_generator.py ← PASTE PROMPT 1.1 code here ⭐
│   └── database/
│       └── models.py               ← Use PROMPT 3.2 schema here
├── frontend/
│   └── src/components/             ← Use PROMPT 3.3 code here
├── docs/
│   ├── MOTIF_DESIGN.md            ← Reference PROMPT 2.1
│   └── PROMPTS.md                 ← Save all prompts here
├── FRICTION_LOG.md                ← Create from PROMPT 4 ⭐
└── PRODUCT_FEEDBACK.md            ← Create from PROMPT 5 ⭐
```

---

## 🚨 COMMON MISTAKES TO AVOID

❌ **Don't**: Use PROMPT 1.1 without customizing context
✅ **Do**: Fill in actual home location, actual baseline patterns

❌ **Don't**: Skip PROMPT 4 (friction log) to save time
✅ **Do**: Add 1 entry every few days = +10% bonus for free

❌ **Don't**: Leave PROMPT 5 (product feedback) until last day
✅ **Do**: Write it as you go, it's easier

❌ **Don't**: Treat prompts as fixed templates
✅ **Do**: Adapt them to your project (e.g., your specific Ring setup)

❌ **Don't**: Copy-paste PROMPT 3.x without reading context
✅ **Do**: Understand the "why" before coding

---

## 🔗 CROSS-REFERENCES

**Need Bedrock explanation code?**
→ PROMPT 1.1 + implementation code + test example

**Need MOTIF algorithm logic?**
→ PROMPT 2.1 + code template + calculation example

**Need help asking Claude for code?**
→ PROMPT 2.2, 3.1, 3.2, 3.3 (these are templates for messaging Claude)

**Need to document problems?**
→ PROMPT 4 (friction log with 3 detailed examples)

**Need final submission text?**
→ PROMPT 5 (Ring, Bedrock, AWS feedback templates)

---

## ⏱️ TIME ESTIMATE PER PROMPT

| Prompt | Read Time | Implement Time | Total |
|--------|-----------|-----------------|-------|
| 1.1 | 5 min | 20 min | 25 min |
| 1.2 | 3 min | 15 min | 18 min |
| 2.1 | 10 min | 30 min | 40 min |
| 2.2 | 2 min | 5 min (messaging) | 7 min |
| 3.1 | 5 min | 30 min | 35 min |
| 3.2 | 5 min | 20 min | 25 min |
| 3.3 | 8 min | 45 min | 53 min |
| 4 | 10 min | 5 min/entry | 60 min total |
| 5 | 5 min | 15 min | 20 min |

**Total implementation time: ~283 minutes = ~4.7 hours**

But you'll be doing this over 28 days, so it averages to **~10 minutes/day**.

---

## 🎯 WINNING STRATEGY

### Week 1 (Days 1-7)
- Use PROMPT 2.1 for team context (Day 1)
- Use PROMPT 3.1 for Ring integration (Day 3-4)

### Week 2 (Days 8-14)
- Use PROMPT 1.1 code for Bedrock (Day 8)
- Use PROMPT 2.2 to debug MOTIF (Days 10-14)
- Start PROMPT 4 friction log (Day 14)

### Week 3 (Days 15-21)
- Use PROMPT 3.2 for database (if not done)
- Use PROMPT 3.3 for dashboard (Day 15-18)
- Add friction log entries (Days 15-20)

### Week 4 (Days 22-28)
- Finalize PROMPT 4 friction log (10 entries, +10% bonus)
- Write PROMPT 5 product feedback (Days 25-27)
- Submit! (Day 28)

---

## 📞 WHEN TO USE WHICH PROMPT

**In your code?**
→ PROMPT 1.1, 1.2, 2.1 (actual implementation code)

**Asking Claude for help?**
→ PROMPT 2.2, 3.1, 3.2, 3.3 (structured templates)

**For hackathon submission?**
→ PROMPT 4, 5 (required + bonus fields)

**For team communication?**
→ PROMPT 2.1 (architecture context)

---

## ✅ BEFORE YOU START

- [ ] Read VIGILANT_Exact_Prompts.md (full version)
- [ ] Print this quick reference
- [ ] Share PROMPTS.md with team
- [ ] Save PROMPT 1.1 code to your IDE
- [ ] Bookmark PROMPT 4 & 5 for later
- [ ] Create `FRICTION_LOG.md` in your repo

---

**You now have everything to build VIGILANT. Go execute.** 🚀
