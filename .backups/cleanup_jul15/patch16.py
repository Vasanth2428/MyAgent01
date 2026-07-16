import os
import re

filepath = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\run_offline_pipeline.py"
with open(filepath, "r") as f:
    content = f.read()

# 1. Give architect 10 tasks
old_tasks = """                tasks=[
                    PlanTaskInput(title="Research UI", domain="design"),
                    PlanTaskInput(title="Scaffold", domain="frontend"),
                    PlanTaskInput(title="Backend Logic", domain="backend")
                ],"""
new_tasks = """                tasks=[
                    PlanTaskInput(title="Task 1", domain="design"),
                    PlanTaskInput(title="Task 2", domain="design"),
                    PlanTaskInput(title="Task 3", domain="frontend"),
                    PlanTaskInput(title="Task 4", domain="backend"),
                    PlanTaskInput(title="Task 5", domain="backend"),
                    PlanTaskInput(title="Task 6", domain="testing"),
                    PlanTaskInput(title="Task 7", domain="frontend"),
                    PlanTaskInput(title="Task 8", domain="testing"),
                    PlanTaskInput(title="Task 9", domain="integration"),
                    PlanTaskInput(title="Task 10", domain="integration")
                ],"""
content = content.replace(old_tasks, new_tasks)

# 2. Fix scraper URL so it skips real scraping
content = content.replace(
    'current_task="Scrape energy saving statistics from https://example.com/smarthome"',
    'current_task="Scrape energy saving statistics from mock-example.com/smarthome"'
)

with open(filepath, "w") as f:
    f.write(content)
print("Applied patch16.py.")
