using UnityEditor;
using UnityEngine;

namespace vortex.EditorTools
{
    /// <summary>
    /// Play を始めたときに、案件のシェーダーの組み合わせ（ShaderVariantCollection）を先にコンパイルする（Editor だけ）。
    ///
    /// Editor は、初めて使う組み合わせをその場でコンパイルする。Blit で描くポストエフェクト（URP の CoreBlit・UberPost、
    /// NiloToon の Uber Post、Crest の水中など）は非同期にならないので、Timeline の途中で初めて使われると Play が止まる。
    /// Play の開始時にまとめてコンパイルしておけば、止まりは開始時の 1 回だけになる。コンパイル済みならすぐ終わる。
    /// ビルドの Graphics 設定の Preloaded Shaders には入れていない（起動が延びる。ビルドで止まりを測ってから決める）。
    ///
    /// コレクションの作り直し: Graphics 設定の「Shader Preloading」の Save to asset と同じ記録を使う
    /// （記録を消す → 各 Timeline を Play で流す → 保存。手順はプロジェクトの CLAUDE.md）。
    /// 切り替え: Window/vortex/Rendering/Shader Warmup On Play（この PC のこのプロジェクトだけに効く。既定は On）。
    /// </summary>
    [InitializeOnLoad]
    public static class ShaderWarmupOnPlay
    {
        private const string CollectionPath = "Assets/03_vortex_live/SinkaiFes2026/Shaders/ShinkaiFes2026.shadervariants";
        private const string MenuPath = "Window/vortex/Rendering/Shader Warmup On Play";
        // EditorPrefs は PC の全プロジェクトで共通なので、プロジェクトのフォルダを鍵に含める（1 つで Off にすると全部 Off になるのを防ぐ）
        private static readonly string PrefKey = "vortex.ShaderWarmupOnPlay.Enabled." + Application.dataPath;

        private static bool Enabled
        {
            get => EditorPrefs.GetBool(PrefKey, true);
            set => EditorPrefs.SetBool(PrefKey, value);
        }

        static ShaderWarmupOnPlay()
        {
            EditorApplication.playModeStateChanged -= OnPlayModeStateChanged;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
        }

        [MenuItem(MenuPath)]
        private static void Toggle() => Enabled = !Enabled;

        [MenuItem(MenuPath, true)]
        private static bool ToggleValidate()
        {
            Menu.SetChecked(MenuPath, Enabled);
            return true;
        }

        /// <summary>切り替えを MCP などから設定する（メニューと同じ）。</summary>
        public static string SetEnabled(bool on)
        {
            Enabled = on;
            return "Shader Warmup On Play: " + (on ? "On" : "Off");
        }

        private static void OnPlayModeStateChanged(PlayModeStateChange change)
        {
            if (change != PlayModeStateChange.EnteredPlayMode || !Enabled) return;
            var collection = AssetDatabase.LoadAssetAtPath<ShaderVariantCollection>(CollectionPath);
            if (collection == null)
            {
                Debug.LogWarning($"[ShaderWarmup] Collection not found: {CollectionPath}. Shaders compile on first use.");
                return;
            }
            var sw = System.Diagnostics.Stopwatch.StartNew();
            collection.WarmUp();
            sw.Stop();
            Debug.Log($"[ShaderWarmup] Warmed up {collection.shaderCount} shaders / {collection.variantCount} variants in {sw.Elapsed.TotalMilliseconds:F0} ms");
        }
    }
}
