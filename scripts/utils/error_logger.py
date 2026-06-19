import traceback
import linecache
import os
import discord
from datetime import datetime

def format_error_report(error: Exception, context: str = "Unknown") -> discord.Embed:
    """
    Creates a detailed error report embed with line tracing and code preview.
    """
    # Get the traceback
    tb = error.__traceback__
    
    if not tb:
        # If no traceback, return a simpler embed
        embed = discord.Embed(
            title="‼️ Error Captured (No Traceback)",
            description=f"**Feature:** {context}\n**Error Type:** `{type(error).__name__}`\n**Message:** `{str(error)}`",
            color=0xff0000,
            timestamp=datetime.now()
        )
        return embed

    # Extract frame info
    # We want the last frame that is inside our project directory
    project_dir = os.getcwd().lower()
    last_project_frame = None
    
    for frame_info in traceback.extract_tb(tb):
        if project_dir in frame_info.filename.lower():
            last_project_frame = frame_info
    
    # If no project frame found, just take the absolute last frame
    if not last_project_frame:
        last_project_frame = traceback.extract_tb(tb)[-1]

    filename = os.path.basename(last_project_frame.filename)
    line_no = last_project_frame.lineno
    func_name = last_project_frame.name
    
    # Get code preview (2 lines before and after)
    preview_lines = []
    start_line = max(1, line_no - 2)
    end_line = line_no + 2
    
    for i in range(start_line, end_line + 1):
        line_content = linecache.getline(last_project_frame.filename, i).strip('\n')
        if i == line_no:
            preview_lines.append(f"> {i:3} | {line_content}")
        else:
            preview_lines.append(f"  {i:3} | {line_content}")
            
    code_preview = "\n".join(preview_lines)
    
    # Build the Embed
    embed = discord.Embed(
        title="‼️ Error Captured",
        description=f"**Feature:** {context}\n**Error Type:** `{type(error).__name__}`\n**Message:** `{str(error)}`",
        color=0xff0000,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📍 Location",
        value=f"File: `{filename}`\nLine: `{line_no}`\nFunction: `{func_name}`",
        inline=False
    )
    
    embed.add_field(
        name="🔍 Line Preview",
        value=f"```python\n{code_preview}\n```",
        inline=False
    )
    
    # Full Traceback (truncated if too long)
    full_tb = "".join(traceback.format_exception(type(error), error, tb))
    if len(full_tb) > 1000:
        full_tb = full_tb[:997] + "..."
        
    embed.add_field(
        name="📜 Full Traceback",
        value=f"```py\n{full_tb}\n```",
        inline=False
    )
    
    return embed
