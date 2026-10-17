import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deeptutor.services.llm import factory
from deeptutor.runtime.agentic import client as agentic
from deeptutor.services.path_service import get_path_service
from deeptutor.services.llm.provider_core.openai_responses.converters import convert_messages

PREFIX = "Educational test context."

class GlobalContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "global_learning_context.md"
        self.path.write_text(PREFIX, encoding="utf-8")
        class_patch_target = type(get_path_service())
        original_get_settings_file = class_patch_target.get_settings_file

        def settings_file(service, name):
            if str(name) == "global_learning_context.md":
                return self.path
            return original_get_settings_file(service, name)

        self.path_patch = patch.object(class_patch_target, "get_settings_file", new=settings_file)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_factory_prefixes_existing_system_without_mutating_history(self):
        history = [{"role":"system","content":"Original role"},{"role":"user","content":"question"}]
        before = copy.deepcopy(history)
        result = factory._build_messages("ignored","ignored",history)
        self.assertTrue(result[0]["content"].startswith(PREFIX))
        self.assertIn("Original role",result[0]["content"])
        self.assertEqual(result[1],history[1])
        self.assertEqual(history,before)

    def test_factory_builds_first_system_without_persona(self):
        result = factory._build_messages("question","Original role",None)
        self.assertTrue(result[0]["content"].startswith(PREFIX))
        self.assertEqual(result[1],{"role":"user","content":"question"})

    def test_user_images_and_tool_protocol_survive_injection(self):
        history = [
            {"role":"user","content":[{"type":"text","text":"Read"},{"type":"image_url","image_url":{"url":"data:image/png;base64,TEST"}}]},
            {"role":"assistant","content":None,"tool_calls":[{"id":"call_1","type":"function","function":{"name":"calc","arguments":"{}"}}]},
            {"role":"tool","tool_call_id":"call_1","content":"2"},
        ]
        result = factory._build_messages("","",history)
        self.assertEqual(result[0]["role"],"system")
        self.assertTrue(result[0]["content"].startswith(PREFIX))
        self.assertEqual(result[1:],history)

    def test_prefix_is_once_and_configuration_reloads(self):
        once=factory._build_messages("q","Role",None)
        twice=factory._build_messages("","",once)
        self.assertEqual(twice,once)
        self.path.write_text("Changed educational context.",encoding="utf-8")
        self.assertTrue(factory._build_messages("q","Role",None)[0]["content"].startswith("Changed educational context."))

    def test_absent_or_empty_configuration_disables_injection(self):
        self.path.unlink()
        expected=[{"role":"system","content":"Role"},{"role":"user","content":"q"}]
        self.assertEqual(factory._build_messages("q","Role",None),expected)
        self.path.write_text(" "*3,encoding="utf-8")
        self.assertEqual(factory._build_messages("q","Role",None),expected)

    def test_responses_keeps_prefix_and_later_summary(self):
        history=[{"role":"system","content":"Original role"},{"role":"system","content":"Conversation summary"},{"role":"user","content":"q"}]
        instructions,items=convert_messages(factory._build_messages("","",history))
        self.assertTrue(instructions.startswith(PREFIX))
        self.assertIn("Original role",instructions)
        self.assertIn("Conversation summary",instructions)
        self.assertEqual(items[0]["content"][0]["text"],"q")

    def test_structured_system_prefix_preserves_blocks_and_is_idempotent(self):
        from deeptutor.services.llm.learning_context import inject_learning_context
        messages=[{"role":"system","content":[{"type":"text","text":"Role","cache_control":{"type":"ephemeral"}}]},{"role":"user","content":"q"}]
        before=copy.deepcopy(messages)
        once=inject_learning_context(messages)
        self.assertEqual(once[0]["content"][0],{"type":"text","text":PREFIX})
        self.assertEqual(once[0]["content"][1:],messages[0]["content"])
        self.assertEqual(inject_learning_context(once),once)
        self.assertEqual(messages,before)
        instructions,_=convert_messages(once)
        self.assertTrue(instructions.startswith(PREFIX))
        self.assertIn("Role",instructions)

    def test_every_installed_persona_and_no_persona_uses_same_prefix(self):
        from deeptutor.services.persona import PersonaService
        from deeptutor.core.context import UnifiedContext
        from deeptutor.agents.loop.prompt_blocks import LoopPromptAssembler
        from deeptutor.capabilities.mastery.pipeline import MasteryPromptAssembler
        personas=PersonaService(root=Path(self.temp.name) / "personas")
        for persona in [""]+[p.name for p in personas.list_personas()]:
            for assembler in (LoopPromptAssembler,MasteryPromptAssembler):
                with self.subTest(persona=persona,assembler=assembler.__name__):
                    original=assembler(prompts={"general":"Base teaching identity"},language="zh").system_prompt(context=UnifiedContext(persona_context=personas.load_for_context(persona)),tool_manifest="calc")
                    result=factory._build_messages("q",original,None)
                    self.assertTrue(result[0]["content"].startswith(PREFIX))
                    self.assertTrue(result[0]["content"].endswith(original))

    def test_actual_factory_complete_and_stream_wire_messages(self):
        import httpx
        from openai import AsyncOpenAI
        from deeptutor.services.llm.provider_core.openai_compat_provider import OpenAICompatProvider
        from deeptutor.services.llm.config import LLMConfig
        captured=[]
        async def handler(request):
            body=json.loads(request.content);captured.append(body)
            if body.get("stream"):
                chunk={"id":"t","object":"chat.completion.chunk","created":0,"model":"test","choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":"stop"}]}
                return httpx.Response(200,text="data: "+json.dumps(chunk)+chr(10)*2+"data: [DONE]"+chr(10)*2,headers={"content-type":"text/event-stream"})
            return httpx.Response(200,json={"id":"t","object":"chat.completion","created":0,"model":"test","choices":[{"index":0,"message":{"role":"assistant","content":"OK"},"finish_reason":"stop"}]})
        async def run():
            provider=OpenAICompatProvider(api_key="test-only",api_base="https://test.invalid/v1",default_model="test",wire_api="chat_completions")
            await provider._client.close()
            provider._client=AsyncOpenAI(api_key="test-only",base_url="https://test.invalid/v1",http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            config=LLMConfig(binding="openai",model="test",api_key="test-only",base_url="https://test.invalid/v1",wire_api="chat_completions")
            with patch.object(factory,"build_isolated_provider",return_value=provider),patch.object(factory,"get_runtime_provider",return_value=provider):
                result=await factory.complete_with_config(config,prompt="q",system_prompt="Format rule",max_retries=0)
                self.assertEqual(result,"OK")
                # complete_with_config closes its isolated client, so give the same
                # real provider a fresh transport for the independent stream.
                provider._client=AsyncOpenAI(api_key="test-only",base_url="https://test.invalid/v1",http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
                chunks=[t async for t in factory.stream("q",system_prompt="Format rule",binding="openai",model="test",api_key="test-only",base_url="https://test.invalid/v1",max_retries=0)]
                self.assertIn("OK","".join(chunks))
            await provider.aclose()
        asyncio.run(run())
        self.assertEqual(len(captured),2)
        for body in captured:
            self.assertTrue(body["messages"][0]["content"].startswith(PREFIX))
            self.assertIn("Format rule",body["messages"][0]["content"])

    def test_agentic_wire_has_prefix_for_stream_and_nonstream(self):
        import httpx
        from openai import AsyncOpenAI
        captured=[]
        async def handler(request):
            payload=json.loads(request.content);captured.append(payload)
            message={"id":"chatcmpl-test","object":"chat.completion","created":0,"model":"test","choices":[{"index":0,"message":{"role":"assistant","content":"OK"},"finish_reason":"stop"}]}
            if payload.get("stream"):
                chunk={"id":"chatcmpl-test","object":"chat.completion.chunk","created":0,"model":"test","choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":"stop"}]}
                return httpx.Response(200,text="data: "+json.dumps(chunk)+chr(10)*2+"data: [DONE]"+chr(10)*2,headers={"content-type":"text/event-stream"})
            return httpx.Response(200,json=message)
        async def run():
            raw=AsyncOpenAI(api_key="test-only",base_url="https://test.invalid/v1",http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            config=agentic.LLMClientConfig(binding="openai",model="test",api_key="test-only",base_url="https://test.invalid/v1")
            history=[{"role":"system","content":"role"},{"role":"user","content":"question"}]
            with patch.object(agentic,"_build_openai_client",return_value=raw):
                client=agentic.build_openai_client(config)
                result=await client.chat.completions.create(model="test",messages=history,stream=False)
                self.assertEqual(result.choices[0].message.content,"OK")
                stream=await client.chat.completions.create(model="test",messages=history,stream=True)
                self.assertEqual("".join([chunk.choices[0].delta.content or "" async for chunk in stream]),"OK")
                self.assertEqual(history[0]["content"],"role")
            await agentic.close_agentic_client_pool()
            await raw.close()
        asyncio.run(run())
        self.assertEqual(len(captured),2)
        for body in captured:
            self.assertTrue(body["messages"][0]["content"].startswith(PREFIX))
            self.assertIn("role",body["messages"][0]["content"])

    def _anthropic_system(self, messages):
        from deeptutor.services.llm.provider_core.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(api_key="test-only", supports_prompt_caching=False)
        system, msgs = provider._convert_messages(factory._build_messages("", "", messages))
        return system, msgs

    def test_anthropic_merges_summary_and_checkpoint_instead_of_overwriting(self):
        history = [
            {"role": "system", "content": "Original role"},
            {"role": "system", "content": "[Conversation summary]\nearlier turns"},
            {"role": "user", "content": "q"},
            {"role": "system", "content": "[Context checkpoint]\nstate"},
        ]
        system, msgs = self._anthropic_system(history)
        self.assertIsInstance(system, str)
        self.assertTrue(system.startswith(PREFIX))
        for part in ("Original role", "earlier turns", "[Context checkpoint]"):
            self.assertIn(part, system)
        self.assertLess(system.index("Original role"), system.index("earlier turns"))
        self.assertTrue(all(m["role"] != "system" for m in msgs))

    def test_anthropic_merges_structured_system_blocks(self):
        history = [
            {"role": "system", "content": [{"type": "text", "text": "Role", "cache_control": {"type": "ephemeral"}}]},
            {"role": "system", "content": "Summary"},
            {"role": "user", "content": "q"},
        ]
        system, _ = self._anthropic_system(history)
        self.assertEqual(system[0], {"type": "text", "text": PREFIX})
        self.assertEqual(system[1], {"type": "text", "text": "Role", "cache_control": {"type": "ephemeral"}})
        self.assertEqual(system[2], {"type": "text", "text": "Summary"})

    def test_anthropic_sonnet5_request_keeps_prefix_and_omits_temperature(self):
        from deeptutor.services.llm.provider_core.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(api_key="test-only")
        messages = factory._build_messages("q", "Role", None)
        kwargs = provider._build_kwargs(messages, None, "claude-sonnet-5", 1024, 0.2, None, None)
        self.assertTrue(kwargs["system"][0]["text"].startswith(PREFIX))
        self.assertIn("Role", kwargs["system"][0]["text"])
        self.assertNotIn("temperature", kwargs.get("extra_body", {}))

if __name__ == "__main__":
    unittest.main()
