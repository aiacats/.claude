// 画面録画（OBS）用に、指定した Display を映す浮動 Game View を置く一時 Editor スクリプト。
// vortex-timeline-export スキルの雛形。案件の Assets/_TempVerify/Editor/ へコピーして使い、録り終えたら削除する。
// MCP の invoke_method から typeName="RecGameView" で呼ぶ。
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;

public static class RecGameView
{
    const BindingFlags kFlags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    const string kTitlePrefix = "RecDisplay";

    static System.Type GameViewType => typeof(EditorWindow).Assembly.GetType("UnityEditor.GameView");

    /// <summary>
    /// 指定した Display を映す浮動 Game View を 1 枚用意し、位置と大きさを決める。
    /// 座標と大きさは Unity の論理座標（表示倍率 100% なら画素と同じ）。
    /// 位置を 2 回当てるのは、作ったばかりの窓は Show 直後の 1 回目の position が効かないため（実測）。
    /// 戻り値の targetSize が Game View の描画の実寸。これが録りたい解像度になっているかを必ず見る。
    /// 注意: Unity は窓を y&lt;0 に置けず 0 に押し戻す。ツールバーを画面の外へ出すには、
    /// windows-gui-testing の gui.ps1 pin で Win32 から窓を動かす（SKILL.md の手順 3）。
    /// </summary>
    public static string PlaceDisplay(int display, float x, float y, float width, float height)
    {
        var type = GameViewType;
        var prop = type.GetProperty("targetDisplay", kFlags);
        if (prop == null) return "GameView.targetDisplay がありません（Unity の版で名前が変わった可能性）";
        string title = kTitlePrefix + display;
        var win = Resources.FindObjectsOfTypeAll(type).Cast<EditorWindow>()
            .FirstOrDefault(w => w.titleContent.text == title);
        if (win == null)
        {
            win = (EditorWindow)ScriptableObject.CreateInstance(type);
            win.titleContent = new GUIContent(title);
            win.Show();
        }
        prop.SetValue(win, display - 1);
        win.position = new Rect(x, y, width, height);
        win.position = new Rect(x, y, width, height);
        win.Repaint();
        var targetSize = type.GetProperty("targetSize", kFlags);
        return $"{title}: display={(int)prop.GetValue(win) + 1} pos={win.position} " +
               $"targetSize={(targetSize != null ? targetSize.GetValue(win) : "n/a")}";
    }

    /// <summary>
    /// 「No cameras rendering」の警告表示を切り替える（Game View の右クリック "Warn if No Cameras Rendering" と同じ）。
    /// Canvas だけが描いている Display では常に出るため、画面録画に映り込む。
    /// </summary>
    public static string SetNoCameraWarning(bool on)
    {
        var field = GameViewType.GetField("m_NoCameraWarning", kFlags);
        if (field == null) return "GameView.m_NoCameraWarning がありません";
        var log = new System.Text.StringBuilder();
        foreach (var w in Resources.FindObjectsOfTypeAll(GameViewType).Cast<EditorWindow>())
        {
            field.SetValue(w, on);
            w.Repaint();
            log.Append($"{w.titleContent.text}={(bool)field.GetValue(w)} ");
        }
        return log.ToString();
    }

    /// <summary>
    /// Timeline を先頭から 1 回だけ再生する（Play 中に呼ぶ）。
    /// 他の Director は止める（同時に動くと DMX とカメラを取り合う）。ループ設定は実行中だけ None にする。
    /// </summary>
    public static string PlayFromStart(string directorName)
    {
        var go = GameObject.Find(directorName);
        if (go == null) return $"見つかりません: {directorName}";
        if (!go.TryGetComponent<PlayableDirector>(out var d)) return $"PlayableDirector がありません: {directorName}";
        foreach (var other in Object.FindObjectsByType<PlayableDirector>(FindObjectsSortMode.None))
            if (other != d) other.Stop();
        d.extrapolationMode = DirectorWrapMode.None;
        d.time = 0;
        d.Evaluate();
        d.Play();
        return $"{directorName}: play from 0 (duration {d.duration:0.00}s)";
    }

    /// <summary>PlaceDisplay で作った浮動 Game View を閉じる。</summary>
    public static string CloseAll()
    {
        int n = 0;
        foreach (var w in Resources.FindObjectsOfTypeAll(GameViewType).Cast<EditorWindow>())
        {
            if (w.titleContent.text.StartsWith(kTitlePrefix, System.StringComparison.Ordinal)) { w.Close(); n++; }
        }
        return $"closed {n}";
    }
}
