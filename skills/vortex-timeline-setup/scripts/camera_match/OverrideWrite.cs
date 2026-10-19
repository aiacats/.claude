// 一時（終わったら消す）。Timeline の Camera グループに、カメラごとの Override Track（全尺 1 クリップ）を組ごとの値で置き直す。
// entries にないカメラの Override Track は、バインドごと消す（記録のままが最良だったカメラ）。
// 同じトラックにクリップを重ねるとブレンドされて重みが割れるため、カメラごとにトラックを分ける（AZKi と同じ形）。
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;
using vortex;

public static class OverrideWrite
{
    const string TrackPrefix = "Override Cam";

    /// <summary>entries: "index:rail:fovOffset" をセミコロン区切り。ラベルはスイッチャーのカメラ名から付ける。</summary>
    public static string Write(string timelinePath, string entries)
    {
        var tl = AssetDatabase.LoadAssetAtPath<TimelineAsset>(timelinePath);
        if (tl == null) return "timeline not found";
        var group = tl.GetRootTracks().OfType<GroupTrack>().FirstOrDefault(g => g.name == "Camera");
        var director = Object.FindObjectsByType<PlayableDirector>(FindObjectsInactive.Include, FindObjectsSortMode.None)
            .FirstOrDefault(d => d.playableAsset == tl);
        var switcher = Object.FindAnyObjectByType<VirtualCameraSwitcher>(FindObjectsInactive.Include);
        if (group == null || director == null || switcher == null) return "group/director/switcher not found";

        var wanted = new Dictionary<int, (float rail, float fov)>();
        foreach (var e in entries.Split(';').Where(s => s.Length > 0))
        {
            var f = e.Split(':');
            wanted[int.Parse(f[0], CultureInfo.InvariantCulture)] =
                (float.Parse(f[1], CultureInfo.InvariantCulture), float.Parse(f[2], CultureInfo.InvariantCulture));
        }

        Undo.RecordObjects(new Object[] { tl, director }, "Write camera override tracks");
        var log = new StringBuilder();
        // 今ある Override Track を index で引けるようにし、要らないものは消す
        var existing = tl.GetOutputTracks().OfType<CameraRecordOverrideTrack>()
            .Where(t => t.name.StartsWith(TrackPrefix, System.StringComparison.Ordinal)).ToList();
        foreach (var t in existing)
        {
            var c = t.GetClips().FirstOrDefault();
            int idx = c != null ? ((CameraRecordOverrideClip)c.asset).offset.targetCameraIndex : -1;
            if (wanted.ContainsKey(idx)) continue;
            string deletedName = t.name; // DeleteTrack の後は破棄済みで読めない
            director.ClearGenericBinding(t);
            tl.DeleteTrack(t);
            log.Append($"deleted {deletedName}; ");
        }
        foreach (var kv in wanted.OrderBy(k => k.Key))
        {
            int index = kv.Key;
            string label = index < switcher._inputCameras.Count && switcher._inputCameras[index] != null ? switcher._inputCameras[index].name : "?";
            string trackName = $"{TrackPrefix}{index:00} {label}";
            var track = tl.GetOutputTracks().OfType<CameraRecordOverrideTrack>()
                            .FirstOrDefault(t => t.GetClips().Any(c => ((CameraRecordOverrideClip)c.asset).offset.targetCameraIndex == index))
                        ?? tl.CreateTrack<CameraRecordOverrideTrack>(group, trackName);
            track.name = trackName;
            var clip = track.GetClips().FirstOrDefault() ?? track.CreateClip<CameraRecordOverrideClip>();
            clip.start = 0;
            clip.duration = tl.duration;
            clip.displayName = string.Format(CultureInfo.InvariantCulture, "rail {0:+0.00;-0.00;0}", kv.Value.rail);
            var asset = (CameraRecordOverrideClip)clip.asset;
            asset.offset.targetCameraIndex = index;
            asset.offset.space = CameraRecordOffsetSpace.CameraLocal;
            asset.offset.railOffset = kv.Value.rail;
            asset.offset.fovOffset = kv.Value.fov;
            asset.offset.rotationOffset = Vector3.zero;
            asset.offset.positionOffset = Vector3.zero;
            EditorUtility.SetDirty(asset);
            EditorUtility.SetDirty(track);
            director.SetGenericBinding(track, switcher);
            log.Append($"{trackName}: rail {kv.Value.rail:+0.00;-0.00;0} fov {kv.Value.fov:+0.00;-0.00;0}; ");
        }
        EditorUtility.SetDirty(tl);
        AssetDatabase.SaveAssets();
        EditorSceneManager.MarkSceneDirty(director.gameObject.scene);
        return log.ToString();
    }
}
