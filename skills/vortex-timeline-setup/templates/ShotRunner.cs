// 雛形（skill vortex-timeline-setup）。案件の Assets/_TempVerify/（Editor の外）へ写し、Play 中に MCP の invoke_method で呼ぶ。終わったら消す。
// Timeline の指定時刻で、番組に出ているカメラ（または PGM / PRV、キャラの前・横からの一時カメラ）の画を PNG で撮る。
// 時刻を合わせたら、その時刻のまま 3 コマ回してからコマの終わりで撮る（キャラのスキンメッシュは次のコマの更新で形が変わるため、
// 時刻を動かした直後に描くと前に撮った時刻のポーズが写る。traps-catalog/unity-timeline.md）。
// 呼び方: Run(<Director の名前>, "t1,t2,...", side, <出力フォルダ>) → State() が "done" か "error: ..." になるまで待つ。RunRange は fps で連番（動画用）。
// 終わった後も Director は Pause のまま（Play を抜ければ戻る）。一時カメラ（side 2・3）は終わると消す。
using System.Collections;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.Playables;
using vortex;

public class ShotRunner : MonoBehaviour
{
    static string s_state = "idle";
    static readonly StringBuilder s_log = new StringBuilder();
    public static string State() => s_state + "\n" + s_log;
    static Animator s_target;

    /// <summary>side 2・3 で寄るキャラ（GameObject のパス。子の Animator を使う）。</summary>
    public static string SetTarget(string path)
    {
        var go = GameObject.Find(path);
        s_target = go != null ? go.GetComponentInChildren<Animator>() : null;
        return s_target != null ? "target " + s_target.name : "not found";
    }

    /// <summary>t0〜t1 秒を fps で撮る（動画にする連番用）。</summary>
    public static string RunRange(string directorName, float t0, float t1, float fps, int side, string outDir)
    {
        if (fps <= 0f || t1 < t0) return "error: t1 >= t0, fps > 0";
        var sb = new StringBuilder();
        int n = Mathf.RoundToInt((t1 - t0) * fps);
        for (int i = 0; i <= n; i++) { if (i > 0) sb.Append(','); sb.Append((t0 + i / (double)fps).ToString("F4", CultureInfo.InvariantCulture)); }
        return Run(directorName, sb.ToString(), side, outDir);
    }

    /// <summary>times: カンマ区切りの秒。side: -1 = 番組に出ている側、0 = A（PGM）、1 = B（PRV）、2 = キャラの前、3 = キャラの右（SetTarget が要る）。</summary>
    public static string Run(string directorName, string times, int side, string outDir)
    {
        // コルーチンは Play 中しか回らない（Edit で呼ぶと running のまま終わらない）
        if (!Application.isPlaying) return "error: play mode only";
        if (s_state == "running") return "error: already running";
        var dirGo = GameObject.Find(directorName);
        if (dirGo == null || !dirGo.TryGetComponent<PlayableDirector>(out var director)) return "error: director not found";
        var switcher = FindAnyObjectByType<VirtualCameraSwitcher>(); // 無効のカメラ群は拾わない（その画は撮れない）
        if (switcher == null) return "error: no active VirtualCameraSwitcher (the camera system is disabled?)";
        if (side >= 2 && s_target == null) return "error: SetTarget first for side 2/3";
        double[] ts;
        try { ts = times.Split(',').Select(s => double.Parse(s, CultureInfo.InvariantCulture)).ToArray(); }
        catch (System.FormatException) { return "error: times must be comma-separated seconds"; }
        s_log.Clear();
        s_state = "running";
        var go = new GameObject("_ShotRunner");
        go.AddComponent<ShotRunner>().StartCoroutine(Go(go, director, switcher, ts, side, outDir));
        return "queued " + ts.Length;
    }

    static IEnumerator Go(GameObject self, PlayableDirector director, VirtualCameraSwitcher switcher, double[] times, int side, string outDir)
    {
        var rt = RenderTexture.GetTemporary(640, 360, 24);
        var tex = new Texture2D(640, 360, TextureFormat.RGB24, false);
        Camera tempCam = null;
        try
        {
            Directory.CreateDirectory(outDir);
            director.Pause();
            for (int n = 0; n < times.Length; n++)
            {
                double t = times[n];
                for (int i = 0; i < 3; i++)
                {
                    director.time = t;
                    director.Evaluate();
                    yield return null;
                }
                director.time = t;
                director.Evaluate();
                yield return new WaitForEndOfFrame();
                bool onB = side < 0 ? VirtualCameraSwitcher.FadeAlpha >= 0.5f : side == 1;
                CameraRecordPlaybackState.TryGet(switcher, out var frame);
                var cam = (onB ? switcher._reserveCamera : switcher._activeCamera).OutputCamera;
                if (side >= 2)
                {
                    // 2 = キャラの前から、3 = キャラの右から（脚の確認用の一時カメラ）。
                    // 2.4 m 離れて画角 35° = 縦 1.5 m（2 × 2.4 × tan 17.5°）を、腰の高さの 6 割を中心に写す → 足元から胸まで
                    if (tempCam == null)
                    {
                        tempCam = new GameObject("_ShotRunnerCam").AddComponent<Camera>();
                        tempCam.CopyFrom(switcher._activeCamera.OutputCamera);
                        tempCam.enabled = false;
                        tempCam.fieldOfView = 35f;
                    }
                    var hips = s_target.GetBoneTransform(HumanBodyBones.Hips);
                    var fwd = Vector3.ProjectOnPlane(hips.forward, Vector3.up).normalized;
                    var dir = side == 2 ? fwd : Vector3.Cross(Vector3.up, fwd);
                    var aim = new Vector3(hips.position.x, hips.position.y * 0.6f, hips.position.z);
                    tempCam.transform.SetPositionAndRotation(aim + dir * 2.4f, Quaternion.LookRotation(-dir, Vector3.up));
                    cam = tempCam;
                }
                var prev = cam.targetTexture;
                cam.targetTexture = rt;
                cam.Render();
                cam.targetTexture = prev;
                RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, 640, 360), 0, 0);
                RenderTexture.active = null;
                File.WriteAllBytes(Path.Combine(outDir, $"{n:000}_{t.ToString("F2", CultureInfo.InvariantCulture)}.png"), tex.EncodeToPNG());
                int idx = frame == null ? -1 : (onB ? frame.Prv.cameraIndex : frame.Pgm.cameraIndex);
                s_log.Append($"{t:F2} {(onB ? "B" : "A")} cam {idx}\n");
            }
            s_state = "done";
        }
        finally
        {
            // 例外でコルーチンが止まっても、running のまま・RT と一時カメラが残ったままにしない
            if (s_state != "done") s_state = "error: stopped (see the Console)";
            RenderTexture.active = null;
            RenderTexture.ReleaseTemporary(rt);
            Destroy(tex);
            if (tempCam != null) Destroy(tempCam.gameObject);
            Destroy(self);
        }
    }
}
