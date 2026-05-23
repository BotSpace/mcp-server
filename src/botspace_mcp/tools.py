"""BotSpace MCP Tool definitions.

Flow manipulation tools (upsert_node, remove_node, connect_nodes,
disconnect_nodes) modify a per-project in-memory working copy.
Use botspace_save_flow to persist, and botspace_deploy to release.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .client import BotSpaceClient, BotSpaceError

# ---------------------------------------------------------------------------
# Node type catalog — 47 node types from engine-golang
# ---------------------------------------------------------------------------
NODE_CATALOG: list[dict] = [
    # ---- Triggers ----------------------------------------------------------
    {
        "type": "startNode",
        "label": "Start / Message Trigger",
        "category": "trigger",
        "description": (
            "Entry point. Triggered when a user sends a message matching the configured "
            "commands or text patterns."
        ),
        "required_data": ["commands"],
        "optional_data": ["match_type"],
        "example_data": {"commands": ["/start"], "match_type": "exact"},
    },
    {
        "type": "callbackTrigger",
        "label": "Callback Query Trigger",
        "category": "trigger",
        "description": "Triggered when a user taps an inline keyboard button (callback_data).",
        "required_data": ["callback_data"],
        "optional_data": [],
        "example_data": {"callback_data": "btn_confirm"},
    },
    {
        "type": "eventTrigger",
        "label": "Event Trigger",
        "category": "trigger",
        "description": (
            "Triggered by Telegram events: new_member, left_member, channel_post, "
            "edited_message, etc."
        ),
        "required_data": ["event_type"],
        "optional_data": [],
        "example_data": {"event_type": "new_member"},
    },
    {
        "type": "webhookTrigger",
        "label": "Webhook Trigger",
        "category": "trigger",
        "description": (
            "Triggered by an incoming HTTP POST to the bot webhook URL. "
            "Receives raw JSON payload accessible via {webhook.*} variables."
        ),
        "required_data": [],
        "optional_data": ["path"],
        "example_data": {"path": "/webhook/payment"},
    },
    {
        "type": "scheduleTrigger",
        "label": "Schedule Trigger",
        "category": "trigger",
        "description": "Triggered on a cron schedule. Runs a flow automatically at set times.",
        "required_data": ["cron"],
        "optional_data": ["timezone"],
        "example_data": {"cron": "0 9 * * *", "timezone": "Asia/Tashkent"},
    },
    # ---- Messages ----------------------------------------------------------
    {
        "type": "sendMessage",
        "label": "Send Message",
        "category": "message",
        "description": (
            "Send a text message to the user. Supports template variables like "
            "{user.first_name}, {env.KEY}. Use parse_mode='HTML' for formatting."
        ),
        "required_data": ["text"],
        "optional_data": ["parse_mode", "disable_web_page_preview"],
        "example_data": {
            "text": "Hello, {user.first_name}!",
            "parse_mode": "HTML",
        },
    },
    {
        "type": "sendPhoto",
        "label": "Send Photo",
        "category": "message",
        "description": "Send a photo (URL or file_id) with optional caption.",
        "required_data": ["photo"],
        "optional_data": ["caption", "parse_mode"],
        "example_data": {
            "photo": "https://example.com/img.jpg",
            "caption": "Here is your image!",
        },
    },
    {
        "type": "sendVideo",
        "label": "Send Video",
        "category": "message",
        "description": "Send a video file by URL or file_id.",
        "required_data": ["video"],
        "optional_data": ["caption", "parse_mode", "supports_streaming"],
        "example_data": {"video": "https://example.com/vid.mp4"},
    },
    {
        "type": "sendDocument",
        "label": "Send Document",
        "category": "message",
        "description": "Send a file/document by URL or file_id.",
        "required_data": ["document"],
        "optional_data": ["caption"],
        "example_data": {"document": "https://example.com/file.pdf"},
    },
    {
        "type": "sendAudio",
        "label": "Send Audio",
        "category": "message",
        "description": "Send an audio file (shown in music player).",
        "required_data": ["audio"],
        "optional_data": ["caption", "title", "performer"],
        "example_data": {"audio": "https://example.com/audio.mp3"},
    },
    {
        "type": "sendVoice",
        "label": "Send Voice",
        "category": "message",
        "description": "Send a voice message (OGG/OPUS format).",
        "required_data": ["voice"],
        "optional_data": ["caption"],
        "example_data": {"voice": "https://example.com/voice.ogg"},
    },
    {
        "type": "sendSticker",
        "label": "Send Sticker",
        "category": "message",
        "description": "Send a sticker by file_id.",
        "required_data": ["sticker"],
        "optional_data": [],
        "example_data": {"sticker": "CAACAgIAAxkBAAIB..."},
    },
    {
        "type": "sendLocation",
        "label": "Send Location",
        "category": "message",
        "description": "Send a geographic location pin.",
        "required_data": ["latitude", "longitude"],
        "optional_data": [],
        "example_data": {"latitude": 41.299496, "longitude": 69.240073},
    },
    {
        "type": "sendContact",
        "label": "Send Contact",
        "category": "message",
        "description": "Send a phone contact card.",
        "required_data": ["phone_number", "first_name"],
        "optional_data": ["last_name"],
        "example_data": {"phone_number": "+998901234567", "first_name": "Support"},
    },
    {
        "type": "sendPoll",
        "label": "Send Poll",
        "category": "message",
        "description": "Send an interactive poll or quiz.",
        "required_data": ["question", "options"],
        "optional_data": ["is_anonymous", "type", "correct_option_id"],
        "example_data": {
            "question": "Which language do you prefer?",
            "options": ["Python", "Go", "JavaScript"],
            "is_anonymous": True,
        },
    },
    {
        "type": "editMessage",
        "label": "Edit Message",
        "category": "message",
        "description": "Edit a previously sent message by message_id.",
        "required_data": ["message_id", "text"],
        "optional_data": ["parse_mode"],
        "example_data": {
            "message_id": "{last_message_id}",
            "text": "Updated text",
        },
    },
    {
        "type": "deleteMessage",
        "label": "Delete Message",
        "category": "message",
        "description": "Delete a message by message_id.",
        "required_data": ["message_id"],
        "optional_data": [],
        "example_data": {"message_id": "{last_message_id}"},
    },
    {
        "type": "forwardMessage",
        "label": "Forward Message",
        "category": "message",
        "description": "Forward a message to another chat.",
        "required_data": ["to_chat_id", "message_id"],
        "optional_data": [],
        "example_data": {
            "to_chat_id": "-100123456789",
            "message_id": "{message.id}",
        },
    },
    {
        "type": "copyMessage",
        "label": "Copy Message",
        "category": "message",
        "description": "Copy a message to another chat (without 'forwarded from' header).",
        "required_data": ["to_chat_id", "message_id"],
        "optional_data": ["caption"],
        "example_data": {"to_chat_id": "-100123456789", "message_id": "{message.id}"},
    },
    # ---- Keyboards ---------------------------------------------------------
    {
        "type": "inlineKeyboard",
        "label": "Inline Keyboard",
        "category": "keyboard",
        "description": (
            "Attach inline buttons to the next message node. "
            "Each button can have callback_data, url, or switch_inline_query."
        ),
        "required_data": ["buttons"],
        "optional_data": [],
        "example_data": {
            "buttons": [
                [
                    {"text": "Yes", "callback_data": "yes"},
                    {"text": "No", "callback_data": "no"},
                ],
                [{"text": "Visit site", "url": "https://botspace.uz"}],
            ]
        },
    },
    {
        "type": "replyKeyboard",
        "label": "Reply Keyboard",
        "category": "keyboard",
        "description": "Show a persistent reply keyboard below the user's input field.",
        "required_data": ["buttons"],
        "optional_data": ["resize_keyboard", "one_time_keyboard", "placeholder"],
        "example_data": {
            "buttons": [["Option 1", "Option 2"], ["Help"]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    },
    {
        "type": "removeKeyboard",
        "label": "Remove Keyboard",
        "category": "keyboard",
        "description": "Remove the current reply keyboard from the user's interface.",
        "required_data": [],
        "optional_data": [],
        "example_data": {},
    },
    # ---- Input / Waiting ---------------------------------------------------
    {
        "type": "waitInput",
        "label": "Wait for User Input",
        "category": "input",
        "description": (
            "Pause the flow and wait for the user's next message. "
            "Save the received value into a named variable. "
            "Optionally timeout after N seconds and jump to another node."
        ),
        "required_data": ["variable"],
        "optional_data": ["timeout_seconds", "timeout_node_id", "validation_regex"],
        "example_data": {
            "variable": "user_phone",
            "timeout_seconds": 120,
        },
    },
    {
        "type": "waitCallback",
        "label": "Wait for Callback",
        "category": "input",
        "description": "Pause and wait for the user to tap an inline keyboard button.",
        "required_data": ["variable"],
        "optional_data": ["timeout_seconds"],
        "example_data": {"variable": "chosen_option"},
    },
    # ---- Logic / Control ---------------------------------------------------
    {
        "type": "condition",
        "label": "Condition (If/Else)",
        "category": "logic",
        "description": (
            "Branch the flow based on a boolean expression. "
            "True path uses source handle 'true', False path uses 'false'. "
            "Supports operators: ==, !=, >, <, >=, <=, contains, in."
        ),
        "required_data": ["expression"],
        "optional_data": [],
        "example_data": {"expression": "{user.language_code} == 'uz'"},
    },
    {
        "type": "switchNode",
        "label": "Switch",
        "category": "logic",
        "description": (
            "Multi-branch switch on a variable value. "
            "Each case maps a value to an output handle name."
        ),
        "required_data": ["variable", "cases"],
        "optional_data": ["default_handle"],
        "example_data": {
            "variable": "{user_choice}",
            "cases": [
                {"value": "A", "handle": "case-A"},
                {"value": "B", "handle": "case-B"},
            ],
            "default_handle": "default",
        },
    },
    {
        "type": "randomBranch",
        "label": "Random Branch",
        "category": "logic",
        "description": "Randomly route to one of N branches (useful for A/B testing).",
        "required_data": ["branches"],
        "optional_data": [],
        "example_data": {
            "branches": [
                {"handle": "branch-1", "weight": 50},
                {"handle": "branch-2", "weight": 50},
            ]
        },
    },
    {
        "type": "delay",
        "label": "Delay",
        "category": "logic",
        "description": "Wait for N seconds before continuing to the next node.",
        "required_data": ["seconds"],
        "optional_data": [],
        "example_data": {"seconds": 3},
    },
    {
        "type": "stopFlow",
        "label": "Stop Flow",
        "category": "logic",
        "description": "Terminate the current flow execution immediately.",
        "required_data": [],
        "optional_data": [],
        "example_data": {},
    },
    {
        "type": "jumpToFlow",
        "label": "Jump to Flow",
        "category": "logic",
        "description": "Transfer execution to another flow (sub-flow call).",
        "required_data": ["target_flow_id"],
        "optional_data": [],
        "example_data": {"target_flow_id": "flow_support"},
    },
    # ---- Variables ---------------------------------------------------------
    {
        "type": "setVariable",
        "label": "Set Variable",
        "category": "variable",
        "description": "Assign a literal value or expression result to a named variable.",
        "required_data": ["variable", "value"],
        "optional_data": [],
        "example_data": {"variable": "counter", "value": "0"},
    },
    {
        "type": "incrementVariable",
        "label": "Increment Variable",
        "category": "variable",
        "description": "Increment a numeric variable by a given amount (default 1).",
        "required_data": ["variable"],
        "optional_data": ["amount"],
        "example_data": {"variable": "counter", "amount": 1},
    },
    {
        "type": "clearVariable",
        "label": "Clear Variable",
        "category": "variable",
        "description": "Delete / reset a variable to null.",
        "required_data": ["variable"],
        "optional_data": [],
        "example_data": {"variable": "temp_data"},
    },
    # ---- HTTP / Integrations -----------------------------------------------
    {
        "type": "httpRequest",
        "label": "HTTP Request",
        "category": "integration",
        "description": (
            "Make an outgoing HTTP request (GET/POST/PUT/PATCH/DELETE) and store the "
            "response body in a variable. Use template variables in URL, headers, body."
        ),
        "required_data": ["url", "method"],
        "optional_data": ["headers", "body", "response_variable", "timeout"],
        "example_data": {
            "url": "https://api.example.com/users",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": "{\"user_id\": \"{user.id}\"}",
            "response_variable": "api_response",
        },
    },
    {
        "type": "jsonParse",
        "label": "JSON Parse",
        "category": "integration",
        "description": (
            "Parse a JSON string variable and extract fields into separate variables "
            "using JSONPath expressions."
        ),
        "required_data": ["source_variable", "mappings"],
        "optional_data": [],
        "example_data": {
            "source_variable": "api_response",
            "mappings": [
                {"path": "$.data.name", "variable": "product_name"},
                {"path": "$.data.price", "variable": "product_price"},
            ],
        },
    },
    # ---- Payments ----------------------------------------------------------
    {
        "type": "sendInvoice",
        "label": "Send Invoice",
        "category": "payment",
        "description": "Send a Telegram Stars or payment provider invoice to the user.",
        "required_data": [
            "title",
            "description",
            "payload",
            "currency",
            "prices",
            "provider_token",
        ],
        "optional_data": [
            "photo_url",
            "need_phone_number",
            "need_email",
            "need_shipping_address",
        ],
        "example_data": {
            "title": "Pro Subscription",
            "description": "30-day pro access",
            "payload": "sub_30d_{user.id}",
            "currency": "UZS",
            "prices": [{"label": "Pro plan", "amount": 5000000}],
            "provider_token": "{env.PAYMENT_TOKEN}",
        },
    },
    {
        "type": "checkPayment",
        "label": "Check Payment (Pre-Checkout)",
        "category": "payment",
        "description": (
            "Validate a pre_checkout_query and confirm or reject payment. "
            "Must be placed after sendInvoice."
        ),
        "required_data": [],
        "optional_data": ["ok", "error_message"],
        "example_data": {"ok": True},
    },
    {
        "type": "paymentSuccess",
        "label": "Payment Success Handler",
        "category": "payment",
        "description": (
            "Triggered after a successful payment. "
            "Provides {payment.total_amount}, {payment.currency}, {payment.payload} variables."
        ),
        "required_data": [],
        "optional_data": [],
        "example_data": {},
    },
    # ---- User / Chat management -------------------------------------------
    {
        "type": "getUserInfo",
        "label": "Get User Info",
        "category": "user",
        "description": "Fetch or refresh Telegram user info, populating {user.*} context variables.",
        "required_data": [],
        "optional_data": ["user_id"],
        "example_data": {},
    },
    {
        "type": "banUser",
        "label": "Ban User",
        "category": "user",
        "description": "Ban a user from a group/channel. Bot must be admin.",
        "required_data": ["user_id"],
        "optional_data": ["chat_id", "until_date", "reason"],
        "example_data": {"user_id": "{user.id}"},
    },
    {
        "type": "unbanUser",
        "label": "Unban User",
        "category": "user",
        "description": "Lift a ban from a user in a group/channel.",
        "required_data": ["user_id"],
        "optional_data": ["chat_id"],
        "example_data": {"user_id": "{user.id}"},
    },
    {
        "type": "muteUser",
        "label": "Mute User",
        "category": "user",
        "description": "Restrict a user from sending messages in a group.",
        "required_data": ["user_id"],
        "optional_data": ["chat_id", "until_date"],
        "example_data": {"user_id": "{user.id}", "until_date": 3600},
    },
    # ---- AI / LLM ----------------------------------------------------------
    {
        "type": "aiReply",
        "label": "AI Reply (LLM)",
        "category": "ai",
        "description": (
            "Generate a reply using an LLM (OpenAI-compatible API). "
            "System prompt, user message, and model are configurable. "
            "Response saved into response_variable."
        ),
        "required_data": ["prompt"],
        "optional_data": [
            "model",
            "system_prompt",
            "temperature",
            "max_tokens",
            "response_variable",
        ],
        "example_data": {
            "prompt": "{user.text}",
            "system_prompt": "You are a helpful assistant for {env.COMPANY_NAME}.",
            "model": "gpt-4o-mini",
            "response_variable": "ai_text",
        },
    },
    {
        "type": "aiClassify",
        "label": "AI Classify",
        "category": "ai",
        "description": (
            "Use an LLM to classify user input into one of N categories. "
            "Result variable contains the matched category name."
        ),
        "required_data": ["text", "categories"],
        "optional_data": ["result_variable", "model"],
        "example_data": {
            "text": "{user.text}",
            "categories": ["support", "sales", "billing", "other"],
            "result_variable": "intent",
        },
    },
    {
        "type": "aiExtract",
        "label": "AI Extract",
        "category": "ai",
        "description": (
            "Use an LLM to extract structured fields from free-form user text. "
            "Results stored as individual variables."
        ),
        "required_data": ["text", "fields"],
        "optional_data": ["model"],
        "example_data": {
            "text": "{user.text}",
            "fields": [
                {"name": "city", "description": "Destination city"},
                {"name": "date", "description": "Travel date"},
            ],
        },
    },
    # ---- Database ----------------------------------------------------------
    {
        "type": "dbQuery",
        "label": "Database Query (SELECT)",
        "category": "database",
        "description": (
            "Execute a SQL SELECT query against the project's connected database. "
            "Results stored as JSON in result_variable."
        ),
        "required_data": ["query"],
        "optional_data": ["params", "result_variable"],
        "example_data": {
            "query": "SELECT * FROM orders WHERE user_id = $1",
            "params": ["{user.id}"],
            "result_variable": "orders",
        },
    },
    {
        "type": "dbWrite",
        "label": "Database Write (INSERT/UPDATE/DELETE)",
        "category": "database",
        "description": "Execute a write SQL statement (INSERT/UPDATE/DELETE).",
        "required_data": ["query"],
        "optional_data": ["params"],
        "example_data": {
            "query": "INSERT INTO users(tg_id, name) VALUES ($1, $2)",
            "params": ["{user.id}", "{user.first_name}"],
        },
    },
    # ---- Admin / Notifications --------------------------------------------
    {
        "type": "notifyAdmin",
        "label": "Notify Admin",
        "category": "admin",
        "description": "Send a notification message to the configured admin chat/channel.",
        "required_data": ["text"],
        "optional_data": ["parse_mode"],
        "example_data": {
            "text": "New user: {user.first_name} ({user.id})",
            "parse_mode": "HTML",
        },
    },
    {
        "type": "broadcastMessage",
        "label": "Broadcast Message",
        "category": "admin",
        "description": (
            "Send a message to all bot users or a filtered segment. "
            "rate_limit controls messages per second."
        ),
        "required_data": ["text"],
        "optional_data": ["filter", "parse_mode", "rate_limit"],
        "example_data": {
            "text": "Important announcement!",
            "filter": {"language_code": "uz"},
            "rate_limit": 30,
        },
    },
    # ---- Groups / Channels ------------------------------------------------
    {
        "type": "checkMembership",
        "label": "Check Channel Membership",
        "category": "group",
        "description": (
            "Check if the user is a member of a channel/group. "
            "Routes via 'member' or 'not_member' output handles."
        ),
        "required_data": ["chat_id"],
        "optional_data": [],
        "example_data": {"chat_id": "@mychannel"},
    },
    {
        "type": "pinMessage",
        "label": "Pin Message",
        "category": "group",
        "description": "Pin a message in the current chat. Bot must be admin.",
        "required_data": ["message_id"],
        "optional_data": ["disable_notification"],
        "example_data": {
            "message_id": "{last_message_id}",
            "disable_notification": False,
        },
    },
]

NODE_TYPE_MAP: dict[str, dict] = {n["type"]: n for n in NODE_CATALOG}

# Trigger node types (for validation)
TRIGGER_TYPES: frozenset[str] = frozenset(
    {n["type"] for n in NODE_CATALOG if n["category"] == "trigger"}
)

# ---------------------------------------------------------------------------
# In-memory working flow store  { project_id -> flow_dict }
# ---------------------------------------------------------------------------
_working_flows: dict[str, dict] = {}


def _flow_key(project_id: Any) -> str:
    return str(project_id)


def _get_working_flow(project_id: Any) -> dict | None:
    return _working_flows.get(_flow_key(project_id))


def _set_working_flow(project_id: Any, flow: dict) -> None:
    _working_flows[_flow_key(project_id)] = flow


async def _load_flow(client: BotSpaceClient, project_id: Any) -> dict:
    key = _flow_key(project_id)
    if key in _working_flows:
        return _working_flows[key]
    flow = await client.get_flow(project_id)
    _working_flows[key] = flow
    return flow


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": msg}, ensure_ascii=False))]


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

# Tools list (populated below, read by @list_tools handler)
_TOOLS: list[Tool] = []

# Dispatch table: tool name -> async handler(arguments) -> list[TextContent]
_HANDLERS: dict[str, Any] = {}


def _tool(tool: Tool):
    """Decorator: registers a tool into _TOOLS and wraps the handler into _HANDLERS."""
    def decorator(fn):
        _TOOLS.append(tool)
        _HANDLERS[tool.name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------

def _get_client(token: str | None = None) -> BotSpaceClient:
    return BotSpaceClient(token=token)


def register_tools(server: Server) -> None:
    client = _get_client()

    # ---- 1. botspace_list_projects ----------------------------------------
    @_tool(Tool(
        name="botspace_list_projects",
        description="List all Telegram bot projects in your BotSpace account.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ))
    async def _list_projects(arguments: dict) -> list[TextContent]:
        try:
            projects = await client.list_projects()
            return _ok({"projects": projects, "count": len(projects)})
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 2. botspace_create_project ---------------------------------------
    @_tool(Tool(
        name="botspace_create_project",
        description="Create a new Telegram bot project in BotSpace.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Bot project name"},
                "description": {"type": "string", "description": "Optional description"},
            },
            "required": ["name"],
        },
    ))
    async def _create_project(arguments: dict) -> list[TextContent]:
        try:
            project = await client.create_project(
                name=arguments["name"],
                description=arguments.get("description", ""),
            )
            return _ok(project)
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 3. botspace_get_flow ---------------------------------------------
    @_tool(Tool(
        name="botspace_get_flow",
        description=(
            "Fetch the bot flow (nodes + edges) from BotSpace and load it into the "
            "local working copy. Call this before making any flow edits."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project / bot ID"},
            },
            "required": ["project_id"],
        },
    ))
    async def _get_flow(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            # Force reload from backend
            _working_flows.pop(_flow_key(project_id), None)
            flow = await _load_flow(client, project_id)
            return _ok({
                "project_id": project_id,
                "nodes_count": len(flow.get("nodes", [])),
                "edges_count": len(flow.get("edges", [])),
                "flow": flow,
            })
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 4. botspace_upsert_node ------------------------------------------
    @_tool(Tool(
        name="botspace_upsert_node",
        description=(
            "Add a new node or update an existing node in the bot flow (in-memory). "
            "Call botspace_list_node_types first to see valid node_type values and required data fields. "
            "Call botspace_save_flow afterward to persist changes to the backend."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "node_id": {
                    "type": "string",
                    "description": (
                        "Node ID. Auto-generated UUID if omitted. "
                        "Provide an existing ID to update that node."
                    ),
                },
                "node_type": {
                    "type": "string",
                    "description": (
                        "Node type from the catalog. Examples: startNode, sendMessage, "
                        "condition, httpRequest, aiReply. "
                        "Call botspace_list_node_types for the full list."
                    ),
                },
                "data": {
                    "type": "object",
                    "description": (
                        "Node configuration. Fields depend on node_type. "
                        "See botspace_list_node_types for required/optional fields and examples."
                    ),
                },
                "position": {
                    "type": "object",
                    "description": "Visual position on canvas {x, y}",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                    },
                },
            },
            "required": ["project_id", "node_type"],
        },
    ))
    async def _upsert_node(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            node_id = arguments.get("node_id") or str(uuid.uuid4())
            node_type = arguments["node_type"]
            data = arguments.get("data") or {}
            position = arguments.get("position") or {"x": 0, "y": 0}

            if node_type not in NODE_TYPE_MAP:
                available = ", ".join(sorted(NODE_TYPE_MAP.keys()))
                return _err(
                    f"Unknown node_type '{node_type}'. "
                    f"Call botspace_list_node_types to see all {len(NODE_TYPE_MAP)} available types. "
                    f"Available: {available}"
                )

            flow = await _load_flow(client, project_id)
            nodes: list = flow.setdefault("nodes", [])

            existing_idx = next(
                (i for i, n in enumerate(nodes) if n.get("id") == node_id), None
            )
            node_obj = {
                "id": node_id,
                "type": node_type,
                "position": position,
                "data": data,
            }
            if existing_idx is not None:
                nodes[existing_idx] = node_obj
                action = "updated"
            else:
                nodes.append(node_obj)
                action = "added"

            _set_working_flow(project_id, flow)
            catalog_entry = NODE_TYPE_MAP[node_type]
            return _ok({
                "action": action,
                "node": node_obj,
                "required_data": catalog_entry["required_data"],
                "missing_required": [
                    f for f in catalog_entry["required_data"]
                    if f not in data or data[f] in (None, "", [])
                ],
                "note": "Call botspace_save_flow to persist changes to backend.",
            })
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 5. botspace_remove_node ------------------------------------------
    @_tool(Tool(
        name="botspace_remove_node",
        description=(
            "Remove a node and all its connected edges from the flow (in-memory). "
            "Call botspace_save_flow afterward to persist."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "node_id": {"type": "string", "description": "ID of the node to remove"},
            },
            "required": ["project_id", "node_id"],
        },
    ))
    async def _remove_node(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            node_id = arguments["node_id"]

            flow = await _load_flow(client, project_id)
            nodes: list = flow.setdefault("nodes", [])
            edges: list = flow.setdefault("edges", [])

            original_nodes = len(nodes)
            original_edges = len(edges)
            flow["nodes"] = [n for n in nodes if n.get("id") != node_id]
            flow["edges"] = [
                e for e in edges
                if e.get("source") != node_id and e.get("target") != node_id
            ]

            removed_nodes = original_nodes - len(flow["nodes"])
            removed_edges = original_edges - len(flow["edges"])
            _set_working_flow(project_id, flow)
            return _ok({
                "removed_nodes": removed_nodes,
                "removed_edges": removed_edges,
                "note": "Call botspace_save_flow to persist.",
            })
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 6. botspace_connect_nodes ----------------------------------------
    @_tool(Tool(
        name="botspace_connect_nodes",
        description=(
            "Add an edge (connection) between two nodes (in-memory). "
            "source_handle defaults to 'source-handler', target_handle to 'target-handler'. "
            "For condition nodes use source_handle='true' or 'false'. "
            "For checkMembership use 'member' or 'not_member'. "
            "Call botspace_save_flow afterward."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "source": {"type": "string", "description": "Source node ID"},
                "target": {"type": "string", "description": "Target node ID"},
                "source_handle": {
                    "type": "string",
                    "description": (
                        "Output handle on the source node. "
                        "Default: 'source-handler'. "
                        "Condition nodes: 'true' or 'false'. "
                        "Switch nodes: match the case handle name."
                    ),
                    "default": "source-handler",
                },
                "target_handle": {
                    "type": "string",
                    "description": "Input handle on the target node. Default: 'target-handler'.",
                    "default": "target-handler",
                },
            },
            "required": ["project_id", "source", "target"],
        },
    ))
    async def _connect_nodes(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            source = arguments["source"]
            target = arguments["target"]
            source_handle = arguments.get("source_handle", "source-handler")
            target_handle = arguments.get("target_handle", "target-handler")

            flow = await _load_flow(client, project_id)
            node_ids = {n.get("id") for n in flow.get("nodes", [])}

            if source not in node_ids:
                return _err(f"Source node '{source}' not found in working flow.")
            if target not in node_ids:
                return _err(f"Target node '{target}' not found in working flow.")

            edge_id = str(uuid.uuid4())
            edge = {
                "id": edge_id,
                "source": source,
                "target": target,
                "sourceHandle": source_handle,
                "targetHandle": target_handle,
            }
            flow.setdefault("edges", []).append(edge)
            _set_working_flow(project_id, flow)
            return _ok({"edge": edge, "note": "Call botspace_save_flow to persist."})
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 7. botspace_disconnect_nodes -------------------------------------
    @_tool(Tool(
        name="botspace_disconnect_nodes",
        description=(
            "Remove an edge by its ID from the flow (in-memory). "
            "Use botspace_get_flow to find edge IDs. "
            "Call botspace_save_flow afterward."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "edge_id": {
                    "type": "string",
                    "description": "Edge ID to remove (visible in flow.edges[].id)",
                },
            },
            "required": ["project_id", "edge_id"],
        },
    ))
    async def _disconnect_nodes(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            edge_id = arguments["edge_id"]

            flow = await _load_flow(client, project_id)
            edges: list = flow.setdefault("edges", [])
            original = len(edges)
            flow["edges"] = [e for e in edges if e.get("id") != edge_id]
            removed = original - len(flow["edges"])
            _set_working_flow(project_id, flow)
            return _ok({
                "removed_edges": removed,
                "note": "Call botspace_save_flow to persist.",
            })
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 8. botspace_validate_flow ----------------------------------------
    @_tool(Tool(
        name="botspace_validate_flow",
        description=(
            "Validate the in-memory working flow. Checks: "
            "trigger node exists, all edges reference valid nodes, "
            "required node data fields are populated. "
            "Returns errors and warnings. Does not modify anything."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
        },
    ))
    async def _validate_flow(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            flow = await _load_flow(client, project_id)
            nodes: list = flow.get("nodes", [])
            edges: list = flow.get("edges", [])

            errors: list[str] = []
            warnings: list[str] = []
            node_ids = {n.get("id") for n in nodes}

            # Must have at least one trigger
            triggers = [n for n in nodes if n.get("type") in TRIGGER_TYPES]
            if not triggers:
                errors.append(
                    "Flow has no trigger node. "
                    "Add a startNode, callbackTrigger, eventTrigger, "
                    "webhookTrigger, or scheduleTrigger."
                )

            # Edges must reference existing nodes
            for edge in edges:
                if edge.get("source") not in node_ids:
                    errors.append(
                        f"Edge '{edge.get('id')}': "
                        f"source node '{edge.get('source')}' does not exist."
                    )
                if edge.get("target") not in node_ids:
                    errors.append(
                        f"Edge '{edge.get('id')}': "
                        f"target node '{edge.get('target')}' does not exist."
                    )

            # Check required data fields
            for node in nodes:
                ntype = node.get("type")
                nid = node.get("id")
                if ntype in NODE_TYPE_MAP:
                    node_data = node.get("data") or {}
                    for field in NODE_TYPE_MAP[ntype].get("required_data", []):
                        if field not in node_data or node_data[field] in (None, "", []):
                            errors.append(
                                f"Node '{nid}' (type={ntype}): "
                                f"missing required field '{field}'."
                            )
                else:
                    warnings.append(
                        f"Node '{nid}' has unrecognized type '{ntype}'."
                    )

            # Orphan nodes (not connected to any edge)
            if len(nodes) > 1:
                connected_ids = set()
                for edge in edges:
                    connected_ids.add(edge.get("source"))
                    connected_ids.add(edge.get("target"))
                for node in nodes:
                    nid = node.get("id")
                    if nid not in connected_ids:
                        warnings.append(
                            f"Node '{nid}' (type={node.get('type')}) "
                            "is not connected to any edge."
                        )

            valid = len(errors) == 0
            return _ok({
                "valid": valid,
                "errors": errors,
                "warnings": warnings,
                "stats": {
                    "nodes": len(nodes),
                    "edges": len(edges),
                    "triggers": len(triggers),
                },
            })
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 9. botspace_save_flow --------------------------------------------
    @_tool(Tool(
        name="botspace_save_flow",
        description=(
            "Persist the in-memory working flow to the BotSpace backend. "
            "Run botspace_validate_flow first to catch errors. "
            "After saving, call botspace_deploy to make the bot live."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
        },
    ))
    async def _save_flow(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            flow = _get_working_flow(project_id)
            if flow is None:
                return _err(
                    "No working flow for this project. "
                    "Call botspace_get_flow first to load it."
                )
            await client.save_flow(project_id, flow)
            return _ok({
                "saved": True,
                "project_id": project_id,
                "nodes": len(flow.get("nodes", [])),
                "edges": len(flow.get("edges", [])),
            })
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 10. botspace_deploy ----------------------------------------------
    @_tool(Tool(
        name="botspace_deploy",
        description=(
            "Deploy (release) the bot to production. "
            "Ensure botspace_save_flow was called first. "
            "The bot becomes live immediately after a successful deploy."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
        },
    ))
    async def _deploy(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            result = await client.deploy(project_id)
            return _ok({"deployed": True, "project_id": project_id, "release": result})
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 11. botspace_list_node_types -------------------------------------
    @_tool(Tool(
        name="botspace_list_node_types",
        description=(
            "List all available node types with descriptions, required/optional data fields, "
            "and example data. Call this before botspace_upsert_node to know what node_type "
            "and data fields to use. "
            "Filter by category: trigger, message, keyboard, input, logic, variable, "
            "integration, payment, user, ai, database, admin, group."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "Optional category filter: "
                        "trigger | message | keyboard | input | logic | variable | "
                        "integration | payment | user | ai | database | admin | group"
                    ),
                },
            },
            "required": [],
        },
    ))
    async def _list_node_types(arguments: dict) -> list[TextContent]:
        category_filter = arguments.get("category")
        catalog = NODE_CATALOG
        if category_filter:
            catalog = [n for n in catalog if n.get("category") == category_filter]
        categories = sorted({n["category"] for n in NODE_CATALOG})
        return _ok({
            "total": len(catalog),
            "categories": categories,
            "node_types": catalog,
        })

    # ---- 12. botspace_set_env ---------------------------------------------
    @_tool(Tool(
        name="botspace_set_env",
        description=(
            "Set or update an environment variable for the bot project. "
            "Variables are accessible in node data as {env.KEY}. "
            "Use for secrets: API keys, payment tokens, etc."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "key": {
                    "type": "string",
                    "description": "Variable name (e.g. PAYMENT_TOKEN, OPENAI_KEY)",
                },
                "value": {"type": "string", "description": "Variable value"},
            },
            "required": ["project_id", "key", "value"],
        },
    ))
    async def _set_env(arguments: dict) -> list[TextContent]:
        try:
            project_id = arguments["project_id"]
            key = arguments["key"]
            value = arguments["value"]
            result = await client.set_env(project_id, key, value)
            return _ok({"set": True, "key": key, "result": result})
        except BotSpaceError as e:
            return _err(str(e))

    # ---- 13. botspace_get_subscription ------------------------------------
    @_tool(Tool(
        name="botspace_get_subscription",
        description=(
            "Get the current BotSpace subscription plan details, "
            "token usage, and resource limits."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ))
    async def _get_subscription(arguments: dict) -> list[TextContent]:
        try:
            sub = await client.get_subscription()
            return _ok(sub)
        except BotSpaceError as e:
            return _err(str(e))

    # ------------------------------------------------------------------
    # Wire list_tools + call_tool handlers onto the server
    # ------------------------------------------------------------------

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return _TOOLS

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = _HANDLERS.get(name)
        if handler is None:
            return _err(f"Unknown tool '{name}'.")
        return await handler(arguments or {})
