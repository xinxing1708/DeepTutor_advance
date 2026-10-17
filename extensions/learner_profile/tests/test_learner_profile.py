"""Synthetic profile tests. Writes only into a temporary settings directory."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deeptutor_learner_profile.extension import LearnerProfileExtension, LearnerProfileUpdate
from deeptutor.core.context import UnifiedContext
from deeptutor.services.path_service import get_path_service


class LearnerProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "learner_profile.md"
        cls = type(get_path_service())
        original = cls.get_settings_file

        def settings_file(service, name):
            return self.path if str(name) == "learner_profile.md" else original(service, name)

        self.patch = patch.object(cls, "get_settings_file", new=settings_file)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.extension = LearnerProfileExtension()
        self.tool = LearnerProfileUpdate()

    def test_profile_is_prompted_for_normal_chat_but_not_partner_or_builtin_users(self):
        normal = UnifiedContext()
        self.assertTrue(self.extension.is_active(normal))
        block = self.extension.system_block(normal, language="zh", prompts={})
        self.assertIn("optional question", block.content)
        self.assertIn("learner_profile_update", block.content)
        self.assertFalse(self.extension.is_active(UnifiedContext(metadata={"agent_identity": {"name": "Tutor"}})))
        self.assertFalse(self.extension.is_active(UnifiedContext(metadata={"learner_profile_prompt": "account profile"})))

    def test_user_consented_fact_is_written_locally_and_injected_next_turn(self):
        context = UnifiedContext(
            user_message="好的，请将它写入我的学习者画像。",
            conversation_history=[{"role": "user", "content": "我喜欢分步骤讲解。"}],
        )
        kwargs = self.extension.augment_kwargs(
            "learner_profile_update",
            {"fact": "我喜欢分步骤讲解。", "consent_quote": "请将它写入我的学习者画像"},
            context,
        )
        result = asyncio.run(self.tool.execute(**kwargs))
        self.assertTrue(result.success, result.content)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "- 我喜欢分步骤讲解。\n")
        block = self.extension.system_block(UnifiedContext(), language="zh", prompts={})
        self.assertIn("我喜欢分步骤讲解。", block.content)

    def test_answering_prompt_does_not_grant_storage_consent(self):
        context = UnifiedContext(user_message="我喜欢分步骤讲解。")
        kwargs = self.extension.augment_kwargs(
            "learner_profile_update",
            {"fact": "我喜欢分步骤讲解。", "consent_quote": "我喜欢分步骤讲解"},
            context,
        )
        result = asyncio.run(self.tool.execute(**kwargs))
        self.assertFalse(result.success)
        self.assertFalse(self.path.exists())

    def test_negative_or_ambiguous_consent_does_not_write(self):
        cases = [
            ("不要把我喜欢分步骤讲解写进画像。", "不要把我喜欢分步骤讲解写进画像"),
            ("如果方便，可以把我喜欢分步骤讲解保存到画像吗？", "如果方便，可以把我喜欢分步骤讲解保存到画像吗？"),
        ]
        for message, quote in cases:
            with self.subTest(message=message):
                result = asyncio.run(self.tool.execute(
                    _user_message=message,
                    _conversation_history=[],
                    fact="我喜欢分步骤讲解",
                    consent_quote=quote,
                ))
                self.assertFalse(result.success)
                self.assertFalse(self.path.exists())

    def test_short_answer_only_confirms_a_clear_prior_profile_question(self):
        history = [
            {"role": "user", "content": "我喜欢分步骤讲解。"},
            {"role": "assistant", "content": "你愿意把这条学习偏好保存到学习者画像吗？"},
        ]
        result = asyncio.run(self.tool.execute(
            _user_message="可以",
            _conversation_history=history,
            fact="我喜欢分步骤讲解。",
            consent_quote="可以",
        ))
        self.assertTrue(result.success, result.content)
        self.assertIn("我喜欢分步骤讲解", self.path.read_text(encoding="utf-8"))

    def test_fact_must_come_from_user_message_not_assistant_text(self):
        context = UnifiedContext(
            user_message="请保存刚才提到的内容到我的学习者画像。",
            conversation_history=[{"role": "assistant", "content": "你可能偏好分步骤讲解。"}],
        )
        kwargs = self.extension.augment_kwargs(
            "learner_profile_update",
            {"fact": "你可能偏好分步骤讲解", "consent_quote": "请保存刚才提到的内容到我的学习者画像"},
            context,
        )
        result = asyncio.run(self.tool.execute(**kwargs))
        self.assertFalse(result.success)
        self.assertFalse(self.path.exists())

    def test_duplicate_fact_is_not_written_twice(self):
        self.path.write_text("- 我喜欢分步骤讲解。\n", encoding="utf-8")
        context = UnifiedContext(
            user_message="请将我喜欢分步骤讲解写入我的学习者画像。",
            conversation_history=[],
        )
        kwargs = self.extension.augment_kwargs(
            "learner_profile_update",
            {"fact": "我喜欢分步骤讲解", "consent_quote": "请将我喜欢分步骤讲解写入我的学习者画像"},
            context,
        )
        result = asyncio.run(self.tool.execute(**kwargs))
        self.assertTrue(result.success, result.content)
        self.assertEqual(self.path.read_text(encoding="utf-8").count("我喜欢分步骤讲解"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
