// 収録モーションの FBX の Avatar の基準の姿勢で、胴・首・頭（と脚）の傾きとねじれを、当てるキャラの基準の姿勢に合わせて取り込み直す。
// マッスルは基準の姿勢からの差なので、基準が倒れていると、まっすぐ立っても傾いて記録される（2026-10-15 MZM・エルセ）。
// 使うとき: 案件の Assets/_TempVerify/Editor/ へ ClipCurveTools.cs と一緒に写して使い、終わったら消す（写し元は ~/.claude/skills/vortex-mocap-fix/templates/Editor）。
// ここは Unity プロジェクトの外の写し元で、Editor フォルダへ写してから使う（trap-ok:cs-runtime-unityeditor）。
// 依存: ClipCurveTools.ReduceLinear、vortex.PosePreset（サブモジュール Submod_RealtimeLiveUtility。HandDump の握りのプリセット）。
// 膝直しはサブモジュールの KneeHyperextensionClamp（mao/knee-muscle-clamp e2d6d889）。
// 間引いた .anim の作り直し: ExtractClip(fbx, out, true)（新しく作る）/ RebuildCurves(fbx, 既存の .anim, 除く名前, 1 以下にする名前)（GUID を保って入れ直す）。
// どちらも FBX をアニメーションの圧縮 Off で取り込んでから（圧縮ありはキーがまばらで断る）。
// 手順: .meta を元に戻す → Run(src, キャラ, true, offsets, 脚も合わせるか, 親指も合わせるか) → ExtractClip → Play / ThumbStats で演者とキャラの平均を比べ、
// 差を offsets に足して繰り返す。作り直したクリップを既存の .anim に入れるなら ReplaceClipContent（GUID が変わらず Timeline の参照がそのまま）
// （claudeLog 2026-10-15 01:15・01:45・02:10）。
// 親指だけ直すとき: .meta を元に戻す → AlignThumbChain(src, キャラ, 左, 右, true, offsets) → TransplantCurves(src, Timeline の .anim, 親指の 4 カーブ, 0.002)
// → ThumbSeries で演者（src を src 自身に当てる）とキャラを比べ、差を offsets に足して繰り返す（claudeLog 2026-10-15 03:xx AZKi）。
using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class BodyRestFix
{
    // 体の向きの枠: 上 = 世界の上、左右 = 腰（左右の脚の付け根）の線を水平にしたもの、前 = 上 × 左右。
    // 区間 a→b の前後の傾き（上から後ろへ倒れる角度、正 = 後ろ）と左右の傾き（正 = 体の左へ）をこの枠で測る
    class Body
    {
        public Transform Hips, Spine, Chest, Neck, Head, HeadEnd, LLeg, RLeg, LArm, RArm, LRoot, RRoot, LFore, RFore, LKnee, RKnee, LFoot, RFoot, LToe, RToe;
        // 脚の向き（比べるだけ）。太もも・すねの向きの単位ベクトルの前・左の成分（下を向くので角度だと ±180° をまたぐ）
        float D(Transform a, Transform b, Vector3 axis) => Vector3.Dot((b.position - a.position).normalized, axis);
        public (string name, System.Func<float> measure)[] Legs() => new (string, System.Func<float>)[]
        {
            ("lThighF", () => D(LLeg, LKnee, Fwd)), ("lThighL", () => D(LLeg, LKnee, Side)),
            ("rThighF", () => D(RLeg, RKnee, Fwd)), ("rThighL", () => D(RLeg, RKnee, Side)),
            ("lShinF", () => D(LKnee, LFoot, Fwd)), ("lShinL", () => D(LKnee, LFoot, Side)),
            ("rShinF", () => D(RKnee, RFoot, Fwd)), ("rShinL", () => D(RKnee, RFoot, Side)),
            // つま先の向き（足首→つま先を水平にして、体の前から何度外へ開くか。正 = 外向き）。内股は脚のねじれでつま先が内へ向く
            ("lToeOut", () => LToeOut), ("rToeOut", () => RToeOut),
            ("lThighPitchD", () => PitchD(LLeg, LKnee)), ("lThighRollD", () => RollD(LLeg, LKnee)),
            ("rThighPitchD", () => PitchD(RLeg, RKnee)), ("rThighRollD", () => RollD(RLeg, RKnee)),
            ("lShinPitchD", () => PitchD(LKnee, LFoot)), ("lShinRollD", () => RollD(LKnee, LFoot)),
            ("rShinPitchD", () => PitchD(RKnee, RFoot)), ("rShinRollD", () => RollD(RKnee, RFoot)),
            ("lKneeOutCm", () => KneeOut(LLeg, LKnee, LFoot, 1f)), ("rKneeOutCm", () => KneeOut(RLeg, RKnee, RFoot, -1f)),
        };
        public Vector3 Side => Vector3.ProjectOnPlane(LLeg.position - RLeg.position, Vector3.up).normalized;
        public Vector3 Fwd => Vector3.Cross(Vector3.up, Side).normalized;
        public float Pitch(Transform a, Transform b) { var v = b.position - a.position; return Mathf.Atan2(Vector3.Dot(v, -Fwd), Vector3.Dot(v, Vector3.up)) * Mathf.Rad2Deg; }
        public float Roll(Transform a, Transform b) { var v = b.position - a.position; return Mathf.Atan2(Vector3.Dot(v, Side), Vector3.Dot(v, Vector3.up)) * Mathf.Rad2Deg; }
        // 肩の付け根（鎖骨の根元）の線が腰の線から水平面で何度回っているか（胴のねじれ、正 = 上から見て反時計回り）。
        // 上腕の位置で測ると、腕の向きを戻したときに胸のねじれと関係なく動くので、胸と一緒に動く付け根で測る
        public float Yaw => Vector3.SignedAngle(Side, Vector3.ProjectOnPlane(LRoot.position - RRoot.position, Vector3.up), Vector3.up);

        // 腕の向き（比べるだけで、合わせる対象にはしない）。上腕の向きの単位ベクトルの前・左・上の成分。
        // 腕は下を向くことが多く、角度で測ると ±180° をまたいで平均が壊れるので成分で比べる
        float C(Transform a, Transform b, Vector3 axis) => Vector3.Dot((b.position - a.position).normalized, axis);
        public (string name, System.Func<float> measure)[] Arms() => new (string, System.Func<float>)[]
        {
            ("lArmF", () => C(LArm, LFore, Fwd)), ("lArmL", () => C(LArm, LFore, Side)), ("lArmU", () => C(LArm, LFore, Vector3.up)),
            ("rArmF", () => C(RArm, RFore, Fwd)), ("rArmL", () => C(RArm, RFore, Side)), ("rArmU", () => C(RArm, RFore, Vector3.up)),
        };

        // 合わせる量の一覧（名前・回す骨・測り方）。下から順に合わせる
        public (string name, Transform bone, System.Func<Vector3> axis, System.Func<float> measure)[] Items() => new (string, Transform, System.Func<Vector3>, System.Func<float>)[]
        {
            ("spinePitch", Spine, () => Side, () => Pitch(Hips, Chest)),
            ("spineRoll", Spine, () => Fwd, () => Roll(Hips, Chest)),
            ("chestPitch", Chest, () => Side, () => Pitch(Chest, Neck)),
            ("chestRoll", Chest, () => Fwd, () => Roll(Chest, Neck)),
            ("chestYaw", Chest, () => (Neck.position - Chest.position).normalized, () => Yaw),
            ("neckPitch", Neck, () => Side, () => Pitch(Neck, Head)),
            ("neckRoll", Neck, () => Fwd, () => Roll(Neck, Head)),
            ("headPitch", Head, () => Side, () => Pitch(Head, HeadEnd)),
            ("headRoll", Head, () => Fwd, () => Roll(Head, HeadEnd)),
        };
        public string Describe() => string.Join(" ", Items().Select(i => $"{i.name} {Safe(i.measure):F1}"));

        // 脚は下を向くので、真下からの傾きで測る。前後 = 下端が前へ出る角度（正 = 前）、左右 = 下端が体の左へ出る角度（正 = 左）
        public float PitchD(Transform a, Transform b) { var v = b.position - a.position; return Mathf.Atan2(Vector3.Dot(v, Fwd), Vector3.Dot(v, -Vector3.up)) * Mathf.Rad2Deg; }
        public float RollD(Transform a, Transform b) { var v = b.position - a.position; return Mathf.Atan2(Vector3.Dot(v, Side), Vector3.Dot(v, -Vector3.up)) * Mathf.Rad2Deg; }
        public float LToeOut => -Vector3.SignedAngle(Fwd, Vector3.ProjectOnPlane(LToe.position - LFoot.position, Vector3.up), Vector3.up);
        public float RToeOut => Vector3.SignedAngle(Fwd, Vector3.ProjectOnPlane(RToe.position - RFoot.position, Vector3.up), Vector3.up);

        // 脚の合わせる量。太もも（付け根の骨）・すね（膝の骨）の前後と左右、つま先の向き（太ももを脚の軸のまわりにねじる。
        // 脚は付け根から外へ回すのが自然な動きで、ねじると膝の向きも一緒に回る）
        public (string name, Transform bone, System.Func<Vector3> axis, System.Func<float> measure)[] LegItems() => new (string, Transform, System.Func<Vector3>, System.Func<float>)[]
        {
            ("lThighPitch", LLeg, () => Side, () => PitchD(LLeg, LKnee)),
            ("lThighRoll", LLeg, () => Fwd, () => RollD(LLeg, LKnee)),
            ("lToeOut", LLeg, () => (LKnee.position - LLeg.position).normalized, () => LToeOut),
            ("lShinPitch", LKnee, () => Side, () => PitchD(LKnee, LFoot)),
            ("lShinRoll", LKnee, () => Fwd, () => RollD(LKnee, LFoot)),
            ("rThighPitch", RLeg, () => Side, () => PitchD(RLeg, RKnee)),
            ("rThighRoll", RLeg, () => Fwd, () => RollD(RLeg, RKnee)),
            ("rToeOut", RLeg, () => (RKnee.position - RLeg.position).normalized, () => RToeOut),
            ("rShinPitch", RKnee, () => Side, () => PitchD(RKnee, RFoot)),
            ("rShinRoll", RKnee, () => Fwd, () => RollD(RKnee, RFoot)),
        };

        // 親指（付け根の骨を回す）。手の枠は Thumb() と同じ: 前 = 手首→中指の付け根、幅 = 小指→人差し指の付け根、法線 = 前 × 幅。
        // 開き = 手のひらの面での前からの角度（法線まわりに回す）、起き = 面からの角度（親指と法線に直交する軸まわりに回す）
        public Transform[] LHandB, RHandB; // 手首・中指・人差し指・小指の付け根・親指の付け根・親指の先
        static (Vector3 fwd, Vector3 across, Vector3 normal, Vector3 th) HandFrame(Transform[] h)
        {
            var fwd = (h[1].position - h[0].position).normalized;
            var across = Vector3.ProjectOnPlane(h[2].position - h[3].position, fwd).normalized;
            return (fwd, across, Vector3.Cross(fwd, across), (h[5].position - h[4].position).normalized);
        }
        static float Spread(Transform[] h) { var f = HandFrame(h); return Mathf.Atan2(Vector3.Dot(f.th, f.across), Vector3.Dot(f.th, f.fwd)) * Mathf.Rad2Deg; }
        static float Out(Transform[] h) { var f = HandFrame(h); return Mathf.Asin(Mathf.Clamp(Vector3.Dot(f.th, f.normal), -1f, 1f)) * Mathf.Rad2Deg; }
        public (string name, Transform bone, System.Func<Vector3> axis, System.Func<float> measure)[] ThumbItems() => new (string, Transform, System.Func<Vector3>, System.Func<float>)[]
        {
            ("lThumbSpread", LHandB[4], () => HandFrame(LHandB).normal, () => Spread(LHandB)),
            ("lThumbOut", LHandB[4], () => Vector3.Cross(HandFrame(LHandB).th, HandFrame(LHandB).normal).normalized, () => Out(LHandB)),
            ("rThumbSpread", RHandB[4], () => HandFrame(RHandB).normal, () => Spread(RHandB)),
            ("rThumbOut", RHandB[4], () => Vector3.Cross(HandFrame(RHandB).th, HandFrame(RHandB).normal).normalized, () => Out(RHandB)),
        };

        // 膝の横のずれ（cm）。膝が「脚の付け根と足首を結ぶ線」から体の外へ何 cm 出ているか（負 = 内 = 内股）
        public float KneeOut(Transform hip, Transform knee, Transform foot, float sign) => Vector3.Dot(knee.position - (hip.position + foot.position) * 0.5f, Side) * sign * 100f;
    }

    static Body Build(GameObject go, HumanDescription hd, bool applySkeleton)
    {
        var all = go.GetComponentsInChildren<Transform>(true).GroupBy(t => t.name).ToDictionary(g => g.Key, g => g.First());
        if (applySkeleton)
            foreach (var sb in hd.skeleton)
            {
                if (!all.TryGetValue(sb.name, out var t) || t == go.transform) continue;
                t.localPosition = sb.position; t.localRotation = sb.rotation; t.localScale = sb.scale;
            }
        Transform B(string human) { var m = hd.human.FirstOrDefault(h => h.humanName == human); return m.boneName != null && all.TryGetValue(m.boneName, out var t) ? t : null; }
        var b = new Body { Hips = B("Hips"), Spine = B("Spine"), Chest = B("Chest"), Neck = B("Neck"), Head = B("Head"),
            LLeg = B("LeftUpperLeg"), RLeg = B("RightUpperLeg"), LArm = B("LeftUpperArm"), RArm = B("RightUpperArm") };
        var ls = B("LeftShoulder"); var rs = B("RightShoulder");
        b.LRoot = ls != null ? ls : b.LArm; b.RRoot = rs != null ? rs : b.RArm; b.LFore = B("LeftLowerArm"); b.RFore = B("RightLowerArm"); b.LKnee = B("LeftLowerLeg"); b.RKnee = B("RightLowerLeg"); b.LFoot = B("LeftFoot"); b.RFoot = B("RightFoot"); b.LToe = B("LeftToes"); b.RToe = B("RightToes");
        // 指は humanName が空白区切り（"Left Thumb Proximal"）。手首は "LeftHand"
        b.LHandB = new[] { "LeftHand", "Left Middle Proximal", "Left Index Proximal", "Left Little Proximal", "Left Thumb Proximal", "Left Thumb Distal" }.Select(B).ToArray();
        b.RHandB = new[] { "RightHand", "Right Middle Proximal", "Right Index Proximal", "Right Little Proximal", "Right Thumb Proximal", "Right Thumb Distal" }.Select(B).ToArray();
        if (b.Head != null) b.HeadEnd = b.Head.Cast<Transform>().FirstOrDefault(c => c.name.EndsWith("HeadEnd", System.StringComparison.Ordinal));
        return b;
    }

    // FBX は中に Avatar を持つ。プレハブ（キャラの _setupped）は持たないので、Animator が参照している Avatar を使う
    static Avatar AvatarOf(string path)
    {
        var av = AssetDatabase.LoadAllAssetsAtPath(path).OfType<Avatar>().FirstOrDefault();
        if (av != null) return av;
        var go = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        var a = go != null ? go.GetComponentInChildren<Animator>(true) : null;
        return a != null ? a.avatar : null;
    }

    // 骨 t を世界の軸 axis まわりに回して measure() を want にする（向きと効き具合は 1 度回して測って決める）
    static void RotateTo(Transform t, Vector3 axis, System.Func<float> measure, float want)
    {
        for (int i = 0; i < 4; i++) // 軸のまわりでほぼ線形なので 1〜2 回で合う。数値誤差のため数回まで
        {
            float now = measure(), d = Mathf.DeltaAngle(now, want);
            if (Mathf.Abs(d) < 0.01f) return;
            var r0 = t.rotation;
            t.rotation = Quaternion.AngleAxis(1f, axis) * r0;
            float slope = Mathf.DeltaAngle(now, measure());
            if (Mathf.Abs(slope) < 1e-3f) return;
            t.rotation = Quaternion.AngleAxis(d / slope, axis) * r0;
        }
    }

    /// <summary>sourceFbx の基準の姿勢の胴・首・頭を targetModel の基準の姿勢と同じ傾き・ねじれにする。apply=false なら測るだけ。
    /// apply=true なら humanDescription を書き換えて取り込み直す。</summary>
    /// offsets（「名前=度;…」）は、キャラの基準の姿勢の値に足す補正。骨の並びの違い（キャラにだけ UpperChest がある等）や、
    /// Unity が体の向きを腰・胸の位置から決めることで残るずれを、演者とキャラの再生中の平均の差から入れる。
    public static string Run(string sourceFbx, string targetModel, bool apply) => Run(sourceFbx, targetModel, apply, "");

    public static string Run(string sourceFbx, string targetModel, bool apply, string offsets) => Run(sourceFbx, targetModel, apply, offsets, false);

    /// legs=true なら脚（太もも・すね・つま先の向き）も合わせる。キャラ側で測れない項目（頭の先の骨が無い等）は合わせない。
    public static string Run(string sourceFbx, string targetModel, bool apply, string offsets, bool legs) => Run(sourceFbx, targetModel, apply, offsets, legs, false);

    /// thumbs=true なら親指の開きと起きも合わせる（エルセは基準の姿勢で親指が手のひらの面に寝ていて、キャラは 14° 起きていた）。
    public static string Run(string sourceFbx, string targetModel, bool apply, string offsets, bool legs, bool thumbs)
    {
        var srcAv = AvatarOf(sourceFbx); var dstAv = AvatarOf(targetModel);
        if (srcAv == null || dstAv == null || !srcAv.isHuman || !dstAv.isHuman) return "missing humanoid avatar";
        var srcHd = srcAv.humanDescription; var dstHd = dstAv.humanDescription;
        var srcGo = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(sourceFbx));
        var dstGo = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(targetModel));
        try
        {
            var s = Build(srcGo, srcHd, true); var d = Build(dstGo, dstHd, true);
            if (s.Spine == null || s.Chest == null || (legs && (s.LToe == null || d.LToe == null))) return "bone not found";
            (string name, Transform bone, System.Func<Vector3> axis, System.Func<float> measure)[] All(Body b) => b.Items().Concat(legs ? b.LegItems() : b.LegItems().Take(0)).Concat(thumbs ? b.ThumbItems() : b.ThumbItems().Take(0)).ToArray();
            string Desc(Body b) => string.Join(" ", All(b).Select(i => $"{i.name} {Safe(i.measure):F1}"));
            var sb = new StringBuilder();
            sb.Append($"target: {Desc(d)}\nbefore: {Desc(s)}\n");
            // 腕の付け根（肩。無ければ上腕）は胸の子なので、胸を回すと一緒に回る。腕と指のマッスルの軸は基準の姿勢の腕の向きから決まるため、
            // 腕まで回すと腕・指のカーブが変わる（指の開きが最大 1.9 動いた）。胴を回した後で、腕の付け根の世界の向きを元に戻す
            var armRoots = new[] { s.LRoot, s.RRoot };
            var armRot0 = armRoots.Select(b => b.rotation).ToArray();
            var bones = new[] { s.Spine, s.Chest, s.Neck, s.Head, s.LRoot, s.RRoot }
                .Concat(legs ? new[] { s.LLeg, s.LKnee, s.RLeg, s.RKnee } : new Transform[0])
                .Concat(thumbs ? new[] { s.LHandB[4], s.RHandB[4] } : new Transform[0]).ToArray();
            var r0 = bones.Select(b => b.localRotation).ToArray();
            var off = (offsets ?? "").Split(';').Where(x => x.Contains("="))
                .ToDictionary(x => x.Split('=')[0].Trim(), x => float.Parse(x.Split('=')[1], System.Globalization.CultureInfo.InvariantCulture));
            var want = All(d).Select(i => Safe(i.measure) + (off.TryGetValue(i.name, out var o) ? o : 0f)).ToArray();
            if (off.Count > 0) sb.Append("offsets: " + string.Join(" ", off.Select(kv => $"{kv.Key} {kv.Value:+0.0;-0.0}")) + "\n");
            var skipped = All(d).Where((it, k) => float.IsNaN(want[k])).Select(it => it.name).ToArray();
            if (skipped.Length > 0) sb.Append("skipped (not measurable on target): " + string.Join(" ", skipped) + "\n");
            // 下の骨を回すと上の区間も動くので、下から順に合わせて 3 巡する
            for (int pass = 0; pass < 3; pass++)
            {
                var items = All(s);
                for (int k = 0; k < items.Length; k++)
                    if (!float.IsNaN(want[k]) && items[k].bone != null) RotateTo(items[k].bone, items[k].axis(), items[k].measure, want[k]);
            }
            for (int i = 0; i < armRoots.Length; i++) armRoots[i].rotation = armRot0[i];
            sb.Append($"after:  {Desc(s)}\nrotated: " + string.Join(" ", bones.Select((b, i) => $"{b.name} {Quaternion.Angle(r0[i], b.localRotation):F1}")) + "\n");
            if (!apply) return sb.ToString();

            var skel = srcHd.skeleton.ToArray();
            for (int i = 0; i < skel.Length; i++)
            {
                var hit = bones.FirstOrDefault(b => b.name == skel[i].name);
                if (hit != null) skel[i].rotation = hit.localRotation;
            }
            srcHd.skeleton = skel;
            var imp = (ModelImporter)AssetImporter.GetAtPath(sourceFbx);
            imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            imp.humanDescription = srcHd;
            imp.SaveAndReimport();
            var av = AvatarOf(sourceFbx);
            sb.Append($"reimported: avatar valid {av != null && av.isValid} human {av != null && av.isHuman}\n");
            return sb.ToString();
        }
        finally { Object.DestroyImmediate(srcGo); Object.DestroyImmediate(dstGo); }
    }

    /// <summary>sourceFbx の基準の姿勢の親指を、付け根・中・先の 3 節それぞれの向き（手の枠での向き）が targetModel の基準の姿勢と同じになるよう回す。
    /// 付け根だけ回す Run(thumbs) は親指全体の向きしか合わず、収録の骨格の中の節の曲がり（AZKi は 35°）が残るため。
    /// 先の節は Distal の子（指先）が両方にあるときだけ合わせる。apply=false なら測るだけ。apply=true なら humanDescription を書き換えて取り込み直す。</summary>
    public static string AlignThumbChain(string sourceFbx, string targetModel, bool left, bool right, bool apply) => AlignThumbChain(sourceFbx, targetModel, left, right, apply, "");

    /// offsets（「lSpread=度;lOut=度;rSpread=…;rOut=…」）は、目標の親指を 3 節まとめて回す量。開き = 手のひらの面で人差し指側へ、起き = 面から法線（前 × 幅）の側へ。
    /// 法線は左手では手の甲側、右手では手のひら側（幅が鏡写しになるため）。ThumbStats / ThumbSeries の out も同じ向きなので、
    /// 合わせた後に残る、キャラと演者の再生中の平均の差（キャラ − 演者）を左右とも符号のまま入れる（基準を開くほど、キャラの親指は閉じる）。
    /// 始める前に .meta を元に戻しておく（今の基準の姿勢から最短で回すので、戻さないと骨のねじれが積み重なる）。
    public static string AlignThumbChain(string sourceFbx, string targetModel, bool left, bool right, bool apply, string offsets)
    {
        var off = (offsets ?? "").Split(';').Where(x => x.Contains("="))
            .ToDictionary(x => x.Split('=')[0].Trim(), x => float.Parse(x.Split('=')[1], System.Globalization.CultureInfo.InvariantCulture));
        float Off(string k) => off.TryGetValue(k, out var v) ? v : 0f;
        var srcAv = AvatarOf(sourceFbx); var dstAv = AvatarOf(targetModel);
        if (srcAv == null || dstAv == null || !srcAv.isHuman || !dstAv.isHuman) return "missing humanoid avatar";
        var srcHd = srcAv.humanDescription; var dstHd = dstAv.humanDescription;
        var srcGo = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(sourceFbx));
        var dstGo = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(targetModel));
        try
        {
            Build(srcGo, srcHd, true); Build(dstGo, dstHd, true);
            var srcAll = srcGo.GetComponentsInChildren<Transform>(true).GroupBy(t => t.name).ToDictionary(g => g.Key, g => g.First());
            var dstAll = dstGo.GetComponentsInChildren<Transform>(true).GroupBy(t => t.name).ToDictionary(g => g.Key, g => g.First());
            Transform B(HumanDescription hd, Dictionary<string, Transform> all, string human)
            {
                var m = hd.human.FirstOrDefault(h => h.humanName == human);
                return m.boneName != null && all.TryGetValue(m.boneName, out var t) ? t : null;
            }
            // 手の枠（Thumb() と同じ）: 前 = 手首→中指の付け根、幅 = 小指→人差し指の付け根、法線 = 前 × 幅（左手は手の甲側、右手は手のひら側）。
            // 指の骨を回しても動かない（手首の子の位置だけで決まる）
            (Vector3 f, Vector3 a, Vector3 n) Frame(HumanDescription hd, Dictionary<string, Transform> all, string side)
            {
                var hand = B(hd, all, side + "Hand").position;
                var f = (B(hd, all, side + " Middle Proximal").position - hand).normalized;
                var a = Vector3.ProjectOnPlane(B(hd, all, side + " Index Proximal").position - B(hd, all, side + " Little Proximal").position, f).normalized;
                return (f, a, Vector3.Cross(f, a));
            }
            var sb = new StringBuilder();
            var changed = new List<Transform>();
            foreach (var side in new[] { "Left", "Right" })
            {
                if ((side == "Left" && !left) || (side == "Right" && !right)) continue;
                var fs = Frame(srcHd, srcAll, side); var fd = Frame(dstHd, dstAll, side);
                var names = new[] { side + " Thumb Proximal", side + " Thumb Intermediate", side + " Thumb Distal" };
                var sBones = names.Select(n => B(srcHd, srcAll, n)).ToArray();
                var dBones = names.Select(n => B(dstHd, dstAll, n)).ToArray();
                if (sBones.Any(x => x == null) || dBones.Any(x => x == null)) { sb.Append($"{side}: thumb bone not found\n"); continue; }
                // 節の終わり: 次の骨、先の節は指先（Distal の子）
                Transform End(Transform[] bones, int i) => i < 2 ? bones[i + 1] : (bones[2].childCount > 0 ? bones[2].GetChild(0) : null);
                Vector3 InFrame((Vector3 f, Vector3 a, Vector3 n) fr, Vector3 v) => new Vector3(Vector3.Dot(v, fr.a), Vector3.Dot(v, fr.f), Vector3.Dot(v, fr.n));
                // 補正: 親指全体（付け根→先の関節。Thumb() の測り方）を、法線まわりに開きの分、法線の側へ起きの分だけ回す回転を、3 節の目標の向きに同じく掛ける
                var key = side == "Left" ? "l" : "r";
                var th = (dBones[2].position - dBones[0].position).normalized;
                var thc = InFrame(fd, th);
                var thSrc = fs.a * thc.x + fs.f * thc.y + fs.n * thc.z;
                var turn = Quaternion.AngleAxis(Off(key + "Out"), Vector3.Cross(Quaternion.AngleAxis(Off(key + "Spread"), fs.n) * thSrc, fs.n).normalized)
                    * Quaternion.AngleAxis(Off(key + "Spread"), fs.n);
                if (Off(key + "Spread") != 0f || Off(key + "Out") != 0f) sb.Append($"{side}: offsets spread {Off(key + "Spread"):+0.0;-0.0} out {Off(key + "Out"):+0.0;-0.0}\n");
                for (int i = 0; i < 3; i++)
                {
                    var se = End(sBones, i); var de = End(dBones, i);
                    if (se == null || de == null) { sb.Append($"{names[i]}: no tip, skipped\n"); continue; }
                    // キャラの節の向きを手の枠の成分にし、収録の骨格の手の枠へ写したものが目標
                    var c = InFrame(fd, (de.position - dBones[i].position).normalized);
                    var wantInSrc = turn * (fs.a * c.x + fs.f * c.y + fs.n * c.z);
                    var now = (se.position - sBones[i].position).normalized;
                    float before = Vector3.Angle(now, wantInSrc);
                    var r0 = sBones[i].localRotation;
                    sBones[i].rotation = Quaternion.FromToRotation(now, wantInSrc) * sBones[i].rotation;
                    float after = Vector3.Angle((se.position - sBones[i].position).normalized, wantInSrc);
                    sb.Append($"{names[i]} ({sBones[i].name}): dir src {InFrame(fs, now):F3} -> target {c:F3}, off {before:F1} -> {after:F2} deg, rotated {Quaternion.Angle(r0, sBones[i].localRotation):F1}\n");
                    changed.Add(sBones[i]);
                }
            }
            if (!apply) return sb.ToString();

            var skel = srcHd.skeleton.ToArray();
            for (int i = 0; i < skel.Length; i++)
            {
                var hit = changed.FirstOrDefault(b => b.name == skel[i].name);
                if (hit != null) skel[i].rotation = hit.localRotation;
            }
            srcHd.skeleton = skel;
            var imp = (ModelImporter)AssetImporter.GetAtPath(sourceFbx);
            imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            imp.humanDescription = srcHd;
            imp.SaveAndReimport();
            var av = AvatarOf(sourceFbx);
            sb.Append($"reimported: avatar valid {av != null && av.isValid} human {av != null && av.isHuman}\n");
            return sb.ToString();
        }
        finally { Object.DestroyImmediate(srcGo); Object.DestroyImmediate(dstGo); }
    }

    /// <summary>srcPath（FBX か .anim）のクリップの Animator のカーブ names（「;」区切り）を、dstPath の .anim の同じカーブへその場で差し替える（GUID と他のカーブはそのまま）。
    /// eps &gt; 0 ならキーを間引く（ClipCurveTools.ReduceLinear、マッスルは 0.002 = 可動域の 0.1%）。差し替え前後の値の差の最大を返す。
    /// 差し替えるカーブは組でしか意味が無い（親指の 4 本は同じ基準の姿勢から作ったもの）ので、1 本でも欠けるか、最初と最後のキーの時刻が
    /// 元と 1 コマ以上ずれていれば、何も書かずに返す。</summary>
    public static string TransplantCurves(string srcPath, string dstPath, string names, float eps)
    {
        var src = AssetDatabase.LoadAllAssetsAtPath(srcPath).OfType<AnimationClip>().FirstOrDefault(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
        var dst = AssetDatabase.LoadAssetAtPath<AnimationClip>(dstPath);
        if (src == null || dst == null) return $"missing clip (src {src != null}, dst {dst != null})";
        var sb = new StringBuilder();
        var bindings = new List<EditorCurveBinding>();
        var curves = new List<AnimationCurve>();
        float frame = 1f / Mathf.Max(1f, dst.frameRate);
        foreach (var name in names.Split(';').Select(x => x.Trim()).Where(x => x.Length > 0))
        {
            var b = EditorCurveBinding.FloatCurve("", typeof(Animator), name);
            var c = AnimationUtility.GetEditorCurve(src, b);
            var old = AnimationUtility.GetEditorCurve(dst, b);
            if (c == null || old == null || c.length == 0 || old.length == 0) return $"{name}: missing (src {c != null}, dst {old != null}), nothing written";
            float s0 = c.keys[0].time, s1 = c.keys[c.length - 1].time, d0 = old.keys[0].time, d1 = old.keys[old.length - 1].time;
            if (Mathf.Abs(s0 - d0) > frame || Mathf.Abs(s1 - d1) > frame) return $"{name}: time range differs (src {s0:F3}-{s1:F3}, dst {d0:F3}-{d1:F3}), nothing written";
            int before = c.length;
            if (eps > 0f)
            {
                if (!IsDense(c, src)) return $"{name}: src has {c.length} keys, not one per frame; import it with animation compression Off. nothing written";
                c = ClipCurveTools.ReduceLinear(c, ReduceEps(name, eps));
            }
            float maxDiff = 0f;
            for (float t = 0f; t < dst.length; t += 0.25f) maxDiff = Mathf.Max(maxDiff, Mathf.Abs(c.Evaluate(t) - old.Evaluate(t)));
            bindings.Add(b); curves.Add(c);
            sb.Append($"{name}: keys {before} -> {c.length} (dst had {old.length}), max change {maxDiff:F3}\n");
        }
        if (bindings.Count == 0) return "no curve names";
        AnimationUtility.SetEditorCurves(dst, bindings.ToArray(), curves.ToArray());
        EditorUtility.SetDirty(dst);
        AssetDatabase.SaveAssets();
        return sb.ToString();
    }

    // 骨が無いモデル（頭の先の骨が無い等）でも他の項目は測れるように、測れない項目は NaN にする
    static float Safe(System.Func<float> f) { try { return f(); } catch (System.NullReferenceException) { return float.NaN; } }

    /// <summary>モデル（FBX・プレハブ）の基準の姿勢（Avatar の skeleton）で、胴・腕・脚の各量を返す。</summary>
    public static string Rest(string modelPath)
    {
        var go = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
        try
        {
            var a = go.GetComponentInChildren<Animator>();
            var body = Build(a.gameObject, a.avatar.humanDescription, true);
            var items = body.Items().Select(i => (i.name, i.measure)).Concat(body.Arms()).Concat(body.Legs()).ToArray();
            return $"{System.IO.Path.GetFileName(modelPath)} rest: " + string.Join(" ", items.Select(it => $"{it.name} {Safe(it.measure):0.00}"));
        }
        finally { Object.DestroyImmediate(go); }
    }

    /// <summary>モデルに clip を step 秒ごとに当て、胴・首・頭の各量の平均を返す（キャラと演者の骨格で比べる）。clipPath が空なら FBX の中のクリップ。</summary>
    public static string Play(string modelPath, string clipPath, float step) => Play(modelPath, clipPath, step, 0f);

    /// <summary>t0 秒から後だけを測る（エルセのように途中から登場する演者は、登場前の姿勢を平均に入れない）。</summary>
    public static string Play(string modelPath, string clipPath, float step, float t0)
    {
        var clip = AssetDatabase.LoadAllAssetsAtPath(string.IsNullOrEmpty(clipPath) ? modelPath : clipPath).OfType<AnimationClip>()
            .First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
        var go = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
        try
        {
            var a = go.GetComponentInChildren<Animator>();
            var body = Build(go, a.avatar.humanDescription, false);
            var items = body.Items().Select(i => (i.name, i.measure)).Concat(body.Arms()).Concat(body.Legs()).ToArray();
            int n = Mathf.FloorToInt((clip.length - t0) / step);
            var sum = new double[items.Length];
            for (int i = 0; i < n; i++)
            {
                clip.SampleAnimation(a.gameObject, t0 + i * step);
                for (int k = 0; k < items.Length; k++) sum[k] += Safe(items[k].measure);
            }
            return $"{System.IO.Path.GetFileName(modelPath)} + {clip.name}: " + string.Join(" ", items.Select((it, k) => $"{it.name} {sum[k] / n:0.00}"));
        }
        finally { Object.DestroyImmediate(go); }
    }

    // 親指の向きを手の枠で測る。手の前 = 手首→中指の付け根、手の幅 = 小指の付け根→人差し指の付け根（手の前に直交させる）、手の甲側 = 前 × 幅。
    // spread = 親指（付け根→先）を手のひらの面に落としたときの、手の前からの角度（人差し指側へ開くほど大きい）。
    // out = 親指が手のひらの面から何度起きているか（正 = 前 × 幅 の向き）
    static (float spread, float outOfPlane) Thumb(Animator a, bool left)
    {
        Transform B(HumanBodyBones b) => a.GetBoneTransform(b);
        var hand = B(left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand);
        var mid = B(left ? HumanBodyBones.LeftMiddleProximal : HumanBodyBones.RightMiddleProximal);
        var idx = B(left ? HumanBodyBones.LeftIndexProximal : HumanBodyBones.RightIndexProximal);
        var lit = B(left ? HumanBodyBones.LeftLittleProximal : HumanBodyBones.RightLittleProximal);
        var t0 = B(left ? HumanBodyBones.LeftThumbProximal : HumanBodyBones.RightThumbProximal);
        var t2 = B(left ? HumanBodyBones.LeftThumbDistal : HumanBodyBones.RightThumbDistal);
        var fwd = (mid.position - hand.position).normalized;
        var across = Vector3.ProjectOnPlane(idx.position - lit.position, fwd).normalized;
        var normal = Vector3.Cross(fwd, across);
        var th = (t2.position - t0.position).normalized;
        float spread = Mathf.Atan2(Vector3.Dot(th, across), Vector3.Dot(th, fwd)) * Mathf.Rad2Deg;
        float outOfPlane = Mathf.Asin(Mathf.Clamp(Vector3.Dot(th, normal), -1f, 1f)) * Mathf.Rad2Deg;
        return (spread, outOfPlane);
    }

    /// <summary>親指の向き（左右の spread・out）を、基準の姿勢と、clip の t0 秒以降の平均・5/95 パーセンタイルで返す。clipPath が空なら FBX の中のクリップ。</summary>
    public static string ThumbStats(string modelPath, string clipPath, float step, float t0)
    {
        var go = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
        try
        {
            var a = go.GetComponentInChildren<Animator>();
            Build(a.gameObject, a.avatar.humanDescription, true);
            var rl = Thumb(a, true); var rr = Thumb(a, false);
            var sb = new StringBuilder($"{System.IO.Path.GetFileName(modelPath)} rest: L spread {rl.spread:F1} out {rl.outOfPlane:F1} / R spread {rr.spread:F1} out {rr.outOfPlane:F1}\n");
            if (step <= 0f) return sb.ToString();
            var clip = AssetDatabase.LoadAllAssetsAtPath(string.IsNullOrEmpty(clipPath) ? modelPath : clipPath).OfType<AnimationClip>()
                .First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
            int n = Mathf.FloorToInt((clip.length - t0) / step);
            var v = new List<float>[4]; for (int k = 0; k < 4; k++) v[k] = new List<float>();
            for (int i = 0; i < n; i++)
            {
                clip.SampleAnimation(a.gameObject, t0 + i * step);
                var l = Thumb(a, true); var r = Thumb(a, false);
                v[0].Add(l.spread); v[1].Add(l.outOfPlane); v[2].Add(r.spread); v[3].Add(r.outOfPlane);
            }
            string S(List<float> x) { var s = x.OrderBy(q => q).ToList(); return $"mean {x.Average():F1} p5 {s[(int)(0.05f * (s.Count - 1))]:F1} p95 {s[(int)(0.95f * (s.Count - 1))]:F1}"; }
            sb.Append($"play ({clip.name}, {t0}s-): L spread {S(v[0])} | L out {S(v[1])} | R spread {S(v[2])} | R out {S(v[3])}\n");
            return sb.ToString();
        }
        finally { Object.DestroyImmediate(go); }
    }

    /// <summary>親指の向き（左右の spread・out）と親指のマッスルを、clip の t0 秒から step 秒ごとに CSV に書く（時刻ごとの変化と、可動域の端に張り付く区間を探す）。</summary>
    public static string ThumbSeries(string modelPath, string clipPath, float step, float t0, string csvPath) => ThumbSeries(modelPath, clipPath, step, t0, -1f, csvPath);

    /// t1 &gt;= 0 なら t1 秒まで（跳びの前後を 1 フレームずつ見る）。
    public static string ThumbSeries(string modelPath, string clipPath, float step, float t0, float t1, string csvPath)
    {
        var go = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
        try
        {
            var a = go.GetComponentInChildren<Animator>();
            var clip = AssetDatabase.LoadAllAssetsAtPath(string.IsNullOrEmpty(clipPath) ? modelPath : clipPath).OfType<AnimationClip>()
                .First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
            var names = new[] { "LeftHand.Thumb.Spread", "LeftHand.Thumb.1 Stretched", "LeftHand.Thumb.2 Stretched", "LeftHand.Thumb.3 Stretched",
                "RightHand.Thumb.Spread", "RightHand.Thumb.1 Stretched", "RightHand.Thumb.2 Stretched", "RightHand.Thumb.3 Stretched" };
            var curves = names.Select(n => AnimationUtility.GetEditorCurve(clip, EditorCurveBinding.FloatCurve("", typeof(Animator), n))).ToArray();
            var sb = new StringBuilder("t,Lspread,Lout,Rspread,Rout," + string.Join(",", names) + "\n");
            int n = Mathf.FloorToInt(((t1 >= 0f ? Mathf.Min(t1, clip.length) : clip.length) - t0) / step);
            for (int i = 0; i < n; i++)
            {
                float t = t0 + i * step;
                clip.SampleAnimation(a.gameObject, t);
                var l = Thumb(a, true); var r = Thumb(a, false);
                sb.Append($"{t:F3},{l.spread:F2},{l.outOfPlane:F2},{r.spread:F2},{r.outOfPlane:F2}," + string.Join(",", curves.Select(c => c != null ? c.Evaluate(t).ToString("F4") : "")) + "\n");
            }
            System.IO.File.WriteAllText(csvPath, sb.ToString());
            return $"{n} rows, curves found {curves.Count(c => c != null)}/{curves.Length}";
        }
        finally { Object.DestroyImmediate(go); }
    }

    /// <summary>手の関節の位置を、手の枠（x = 人差し指側、y = 手首→中指の付け根、z = 手の甲側。長さは手首→中指の付け根を 1）で CSV に追記する。
    /// 指は Proximal・Intermediate・Distal と、Distal の子（指先。あれば）。clipPath が空なら FBX の中のクリップ、t &lt; 0 なら基準の姿勢。</summary>
    public static string HandDump(string modelPath, string clipPath, float t, bool left, string tag, string csvPath) => HandDump(modelPath, clipPath, t, left, tag, csvPath, "");

    /// posePresetPath を渡すと、クリップを当てた後にその PosePreset を重み 1 で掛けてから測る（シーンでマイクの握りのプリセットが指を上書きする状態）。
    public static string HandDump(string modelPath, string clipPath, float t, bool left, string tag, string csvPath, string posePresetPath)
    {
        var go = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
        try
        {
            var a = go.GetComponentInChildren<Animator>();
            if (t < 0f) Build(a.gameObject, a.avatar.humanDescription, true);
            else
            {
                var clip = AssetDatabase.LoadAllAssetsAtPath(string.IsNullOrEmpty(clipPath) ? modelPath : clipPath).OfType<AnimationClip>()
                    .First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
                clip.SampleAnimation(a.gameObject, t);
            }
            if (!string.IsNullOrEmpty(posePresetPath))
            {
                var preset = AssetDatabase.LoadAssetAtPath<vortex.PosePreset>(posePresetPath);
                if (preset == null) return "no pose preset: " + posePresetPath;
                preset.ApplyPose(a, 1f);
            }
            string S = left ? "Left" : "Right";
            Transform B(string n) => a.GetBoneTransform((HumanBodyBones)System.Enum.Parse(typeof(HumanBodyBones), S + n));
            var hand = B("Hand"); var mid = B("MiddleProximal"); var idx = B("IndexProximal"); var lit = B("LittleProximal");
            var fwd = mid.position - hand.position; float len = fwd.magnitude; fwd /= len;
            var across = Vector3.ProjectOnPlane(idx.position - lit.position, fwd).normalized;
            var back = left ? Vector3.Cross(fwd, across) : Vector3.Cross(across, fwd);
            var sb = new StringBuilder();
            void P(string name, Transform x)
            {
                if (x == null) return;
                var v = (x.position - hand.position) / len;
                sb.Append($"{tag},{name},{Vector3.Dot(v, across):F4},{Vector3.Dot(v, fwd):F4},{Vector3.Dot(v, back):F4}\n");
            }
            P("wrist", hand);
            foreach (var f in new[] { "Thumb", "Index", "Middle", "Ring", "Little" })
            {
                P(f + "1", B(f + "Proximal")); P(f + "2", B(f + "Intermediate"));
                var dist = B(f + "Distal"); P(f + "3", dist);
                if (dist != null && dist.childCount > 0) P(f + "4", dist.GetChild(0));
            }
            if (!System.IO.File.Exists(csvPath)) System.IO.File.WriteAllText(csvPath, "tag,joint,x,y,z\n");
            System.IO.File.AppendAllText(csvPath, sb.ToString());
            return $"{tag}: {sb.ToString().Split('\n').Length - 1} joints";
        }
        finally { Object.DestroyImmediate(go); }
    }

    /// <summary>srcPath のクリップを複製し、指定の Animator のカーブの値を「scale × (値 − center) + center + shift」にして [min, max] に収め、dstPath に保存する。
    /// spec は「カーブ名=scale,center,shift,min,max;…」（例: "LeftHand.Thumb.Spread=0.6,0.12,-0.3,-1,1"）。振れ幅を縮めて中心を寄せる（親指の開きを抑える）ため。</summary>
    public static string TransformCurves(string srcPath, string dstPath, string spec)
    {
        var src = AssetDatabase.LoadAssetAtPath<AnimationClip>(srcPath);
        if (src == null) return "no clip";
        if (AssetDatabase.LoadAssetAtPath<AnimationClip>(dstPath) != null) AssetDatabase.DeleteAsset(dstPath);
        var copy = Object.Instantiate(src);
        copy.name = System.IO.Path.GetFileNameWithoutExtension(dstPath);
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        var sb = new StringBuilder();
        foreach (var item in spec.Split(';').Where(x => x.Contains("=")))
        {
            var name = item.Split('=')[0].Trim();
            var p = item.Split('=')[1].Split(',').Select(v => float.Parse(v, inv)).ToArray();
            float scale = p[0], center = p[1], shift = p[2], min = p[3], max = p[4];
            var b = EditorCurveBinding.FloatCurve("", typeof(Animator), name);
            var c = AnimationUtility.GetEditorCurve(copy, b);
            if (c == null) { sb.Append($"{name}: missing\n"); continue; }
            var keys = c.keys;
            int clamped = 0;
            for (int i = 0; i < keys.Length; i++)
            {
                float v = scale * (keys[i].value - center) + center + shift;
                if (v < min || v > max) { v = Mathf.Clamp(v, min, max); clamped++; keys[i].inTangent = 0f; keys[i].outTangent = 0f; }
                else { keys[i].inTangent *= scale; keys[i].outTangent *= scale; }
                keys[i].value = v;
            }
            c.keys = keys;
            AnimationUtility.SetEditorCurve(copy, b, c);
            sb.Append($"{name}: {keys.Length} keys, {clamped} clamped\n");
        }
        AssetDatabase.CreateAsset(copy, dstPath);
        AssetDatabase.SaveAssets();
        return sb.ToString();
    }

    /// <summary>Timeline のアニメーションクリップごとに、参照しているアニメーションのパスを返す（外れていれば MISSING）。</summary>
    public static string TimelineClips(string timelinePath)
    {
        var tl = AssetDatabase.LoadAssetAtPath<UnityEngine.Timeline.TimelineAsset>(timelinePath);
        if (tl == null) return "no timeline";
        var sb = new StringBuilder();
        foreach (var track in tl.GetOutputTracks().OfType<UnityEngine.Timeline.AnimationTrack>())
            foreach (var c in track.GetClips())
            {
                var pa = c.asset as UnityEngine.Timeline.AnimationPlayableAsset;
                var clip = pa != null ? pa.clip : null;
                var so = pa != null ? new SerializedObject(pa).FindProperty("m_Clip") : null;
                int id = so != null ? so.objectReferenceInstanceIDValue : 0;
                sb.Append($"{track.name}/{c.displayName}: {(clip != null ? AssetDatabase.GetAssetPath(clip) : "MISSING (instanceID " + id + ")")}\n");
            }
        return sb.ToString();
    }

    /// <summary>srcPath のクリップの中身を dstPath のクリップへ写す（dst の GUID と名前は変えないので、Timeline などの参照はそのまま）。src は消す。</summary>
    public static string ReplaceClipContent(string srcPath, string dstPath)
    {
        // src は最後に消すので、.anim だけを受ける（FBX を渡すと中のクリップを読めてしまい、FBX ごと消える）
        if (!srcPath.EndsWith(".anim", System.StringComparison.OrdinalIgnoreCase) || !dstPath.EndsWith(".anim", System.StringComparison.OrdinalIgnoreCase))
            return "error: src and dst must be .anim (src is deleted afterwards)";
        if (string.Equals(srcPath, dstPath, System.StringComparison.OrdinalIgnoreCase)) return "error: src and dst are the same";
        var src = AssetDatabase.LoadAssetAtPath<AnimationClip>(srcPath);
        var dst = AssetDatabase.LoadAssetAtPath<AnimationClip>(dstPath);
        if (src == null || dst == null) return "missing clip";
        var name = dst.name;
        EditorUtility.CopySerialized(src, dst);
        dst.name = name;
        EditorUtility.SetDirty(dst);
        AssetDatabase.SaveAssetIfDirty(dst); // SaveAssets は関係ない dirty なアセットまで保存する
        AssetDatabase.DeleteAsset(srcPath);
        return $"{srcPath} -> {dstPath} ({dst.length:F2}s, guid {AssetDatabase.AssetPathToGUID(dstPath)})";
    }

    /// <summary>同じモデルに clipA と clipB を当て、主な骨の世界の位置の差（cm）の平均と 99 パーセンタイルを返す（直したところ以外が動いていないかを見る）。</summary>
    public static string WorldDiff(string modelPath, string clipA, string clipB, float step)
    {
        AnimationClip L(string p) => AssetDatabase.LoadAllAssetsAtPath(p).OfType<AnimationClip>().First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
        var ca = L(clipA); var cb = L(clipB);
        var ga = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
        var gb = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
        try
        {
            var aa = ga.GetComponentInChildren<Animator>(); var ab = gb.GetComponentInChildren<Animator>();
            var ids = new[] { HumanBodyBones.Hips, HumanBodyBones.LeftFoot, HumanBodyBones.RightFoot, HumanBodyBones.LeftHand, HumanBodyBones.RightHand,
                HumanBodyBones.LeftIndexDistal, HumanBodyBones.RightIndexDistal, HumanBodyBones.LeftLittleDistal, HumanBodyBones.RightLittleDistal, HumanBodyBones.Head };
            int n = Mathf.FloorToInt(Mathf.Min(ca.length, cb.length) / step);
            var d = ids.Select(_ => new List<float>()).ToArray();
            var dy = ids.Select(_ => new List<float>()).ToArray(); // 高さの差（cm、b − a）。Foot IK Off のとき足が浮く・沈むかを見る
            for (int i = 0; i < n; i++)
            {
                ca.SampleAnimation(aa.gameObject, i * step); cb.SampleAnimation(ab.gameObject, i * step);
                for (int k = 0; k < ids.Length; k++)
                {
                    var x = aa.GetBoneTransform(ids[k]); var y = ab.GetBoneTransform(ids[k]);
                    if (x != null && y != null) { d[k].Add((x.position - y.position).magnitude * 100f); dy[k].Add((y.position.y - x.position.y) * 100f); }
                }
            }
            return string.Join("\n", ids.Select((id, k) => d[k].Count == 0 ? $"{id}: -" :
                $"{id}: mean {d[k].Average():F1} p99 {d[k].OrderBy(v => v).ElementAt((int)(0.99f * (d[k].Count - 1))):F1} dY mean {dy[k].Average():+0.0;-0.0} min {dy[k].Min():+0.0;-0.0} max {dy[k].Max():+0.0;-0.0}"));
        }
        finally { Object.DestroyImmediate(ga); Object.DestroyImmediate(gb); }
    }

    /// <summary>2 本のクリップの足の IK の目標（RootT + RootQ × FootT、Humanoid の正規化した長さ）の差を、humanScale を掛けて cm で返す。
    /// Foot IK が On のとき、舞台の上の足はこの目標に置かれる。</summary>
    public static string GoalDiff(string clipA, string clipB, float humanScale, float step)
    {
        AnimationClip L(string p) => AssetDatabase.LoadAllAssetsAtPath(p).OfType<AnimationClip>().First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
        AnimationCurve G(AnimationClip c, string n) => AnimationUtility.GetEditorCurve(c, EditorCurveBinding.FloatCurve("", typeof(Animator), n));
        Vector3 Goal(AnimationClip c, string foot, float t)
        {
            var rt = new Vector3(G(c, "RootT.x").Evaluate(t), G(c, "RootT.y").Evaluate(t), G(c, "RootT.z").Evaluate(t));
            var rq = new Quaternion(G(c, "RootQ.x").Evaluate(t), G(c, "RootQ.y").Evaluate(t), G(c, "RootQ.z").Evaluate(t), G(c, "RootQ.w").Evaluate(t)).normalized;
            var ft = new Vector3(G(c, foot + "T.x").Evaluate(t), G(c, foot + "T.y").Evaluate(t), G(c, foot + "T.z").Evaluate(t));
            return rt + rq * ft;
        }
        var a = L(clipA); var b = L(clipB);
        int n = Mathf.FloorToInt(Mathf.Min(a.length, b.length) / step);
        var sb = new StringBuilder();
        foreach (var foot in new[] { "LeftFoot", "RightFoot" })
        {
            var d = new List<float>();
            for (int i = 0; i < n; i++) d.Add((Goal(a, foot, i * step) - Goal(b, foot, i * step)).magnitude * humanScale * 100f);
            d.Sort();
            sb.Append($"{foot} goal: mean {d.Average():F2}cm p99 {d[(int)(0.99f * (d.Count - 1))]:F2}cm\n");
        }
        return sb.ToString();
    }

    /// <summary>FBX の中のクリップを .anim に書き出す（既にあれば書かない）。実行用と編集用の両方のカーブを持たせる。</summary>
    public static string ExtractClip(string fbxPath, string outPath) => ExtractClip(fbxPath, outPath, false);

    /// <summary>
    /// 間引きの許容値。マッスルは muscleEps（0.002 = 可動域の 0.1%）。Root と IK の目標（RootT/Q・*FootT/Q・*HandT/Q）は
    /// 足の位置に直に効くので、マッスルと同じ許容だと足が数 mm 揺れる（RootQ の 0.002 は約 0.2° で、腰から 1 m 下の足が約 4 mm 動く。
    /// 2026-10-15 AZKi・エルセ・きまゆで、接地中の足の 1 コマの急な動きが元の 6〜100 倍になった）。
    /// 下の値は、足の目標の誤差が 0.3 mm 以内・揺れが元と同じになることを AZKi の全編で確かめた値（長さは Humanoid の正規化した単位で ≒ m）。
    /// </summary>
    static float ReduceEps(string property, float muscleEps)
    {
        // 脚のマッスル（太もも・すね・足首・つま先）は、Foot IK Off のキャラでは股関節からの積み重ねで足の位置を決める。
        // 0.002 は太ももで約 0.15°、足首で約 2〜3 mm になり、着いている足がガタつく（エルセ。1e-4 で元の FBX と同じ揺れに戻った）
        if (property.StartsWith("Left Upper Leg", System.StringComparison.Ordinal) || property.StartsWith("Right Upper Leg", System.StringComparison.Ordinal) ||
            property.StartsWith("Left Lower Leg", System.StringComparison.Ordinal) || property.StartsWith("Right Lower Leg", System.StringComparison.Ordinal) ||
            property.StartsWith("Left Foot ", System.StringComparison.Ordinal) || property.StartsWith("Right Foot ", System.StringComparison.Ordinal) ||
            property.StartsWith("Left Toes", System.StringComparison.Ordinal) || property.StartsWith("Right Toes", System.StringComparison.Ordinal))
            return Mathf.Min(muscleEps, 1e-4f);
        bool goal = property.StartsWith("Root", System.StringComparison.Ordinal) ||
                    property.StartsWith("LeftFoot", System.StringComparison.Ordinal) || property.StartsWith("RightFoot", System.StringComparison.Ordinal) ||
                    property.StartsWith("LeftHandT", System.StringComparison.Ordinal) || property.StartsWith("LeftHandQ", System.StringComparison.Ordinal) ||
                    property.StartsWith("RightHandT", System.StringComparison.Ordinal) || property.StartsWith("RightHandQ", System.StringComparison.Ordinal);
        if (!goal) return muscleEps;
        if (property.StartsWith("RootQ", System.StringComparison.Ordinal)) return 5e-5f; // 腰から足まで約 1 m なので、0.1 mm 未満
        return property.Contains("Q.") ? 5e-4f : 1e-4f;  // 足・手の向き（つま先まで約 0.15 m）/ 位置（≒0.1 mm）
    }

    /// <summary>
    /// ReduceLinear は「キーが毎フレームある」前提（残したキーの間を直線で結ぶ）。圧縮して取り込んだ FBX のキーはまばらで、
    /// 間の曲線の形を接線で持っているので、直線で結ぶと形が崩れる（AZKi の足の目標が最大 84 mm ずれた。2026-10-15）。
    /// まばらなら、FBX のアニメーションの圧縮を Off にして取り込み直してから使う。
    /// </summary>
    static bool IsDense(AnimationCurve c, AnimationClip clip) => c.length >= Mathf.FloorToInt(clip.length * clip.frameRate);

    /// thin=true ならキーを間引く（エルセの FBX は削減 Off で、そのまま写すと「Object size is too large」で保存できない）。
    /// 許容は ReduceEps（マッスル 0.002、Root と IK の目標はそれより細かく）。キーが毎フレームない（圧縮して取り込んだ）FBX は間引かずに断る。
    public static string ExtractClip(string fbxPath, string outPath, bool thin)
    {
        if (AssetDatabase.LoadAssetAtPath<AnimationClip>(outPath) != null) return "exists: " + outPath;
        var src = AssetDatabase.LoadAllAssetsAtPath(fbxPath).OfType<AnimationClip>()
            .First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
        // CopySerialized だと FBX のクリップは実行用のカーブしか写らない（m_EditorCurves が空）
        var dst = new AnimationClip { frameRate = src.frameRate, name = System.IO.Path.GetFileNameWithoutExtension(outPath) };
        var bindings = AnimationUtility.GetCurveBindings(src);
        var sparse = thin ? bindings.FirstOrDefault(b => !IsDense(AnimationUtility.GetEditorCurve(src, b), src)) : default;
        if (thin && sparse.propertyName != null) return $"{sparse.propertyName}: not one key per frame; import {fbxPath} with animation compression Off. nothing written";
        int before = 0, after = 0;
        var curves = bindings.Select(b =>
        {
            var c = AnimationUtility.GetEditorCurve(src, b);
            before += c.length;
            if (thin) c = ClipCurveTools.ReduceLinear(c, ReduceEps(b.propertyName, 0.002f));
            after += c.length;
            return c;
        }).ToArray();
        AnimationUtility.SetEditorCurves(dst, bindings, curves);
        Debug.Log($"[BodyRestFix] {outPath}: keys {before} -> {after}");
        AnimationUtility.SetAnimationClipSettings(dst, AnimationUtility.GetAnimationClipSettings(src));
        AssetDatabase.CreateAsset(dst, outPath);
        AssetDatabase.SaveAssets();
        return $"{src.name} -> {outPath} ({dst.length:F2}s)";
    }

    /// <summary>
    /// srcPath（圧縮 Off で取り込んだ FBX のクリップ）の Animator のカーブのうち、exclude（「;」区切りの名前の頭）で始まらないものを、
    /// dstPath の既存の .anim の同じカーブへ入れ直す（GUID・exclude のカーブ・クリップの設定はそのまま。Timeline の参照も変わらない）。
    /// 許容は ReduceEps（マッスル 0.002、Root と足・手の目標・脚のマッスルは細かく）。clamp（「;」区切りの名前）のカーブは、間引く前に値を 1 以下にする
    /// （膝直しと同じ上限。毎フレームのキーを直線で結ぶので、キーを 1 以下にすれば区間の途中も 1 を越えない）。
    /// 1 本でも dst に無い・src がまばら・最初と最後のキーの時刻が 1 コマ以上ずれていれば、何も書かずに返す。
    /// 例（2026-10-15 AZKi）: exclude = "Left Arm ;Left Forearm ;Left Hand ;LeftHand."（手で直した左腕・左手を残す）、clamp = "Left Lower Leg Stretch;Right Lower Leg Stretch"。
    /// </summary>
    public static string RebuildCurves(string srcPath, string dstPath, string exclude, string clamp)
    {
        var src = ClipCurveTools.Load(srcPath);
        var dst = AssetDatabase.LoadAssetAtPath<AnimationClip>(dstPath);
        if (src == null || dst == null) return $"missing clip (src {src != null}, dst {dst != null})";
        var ex = exclude.Split(';').Where(x => x.Length > 0).ToArray();
        var cl = clamp.Split(';').Where(x => x.Length > 0).ToArray();
        float frame = 1f / Mathf.Max(1f, dst.frameRate);
        var bindings = new List<EditorCurveBinding>();
        var curves = new List<AnimationCurve>();
        int skipped = 0, keysBefore = 0, keysAfter = 0, clampedKeys = 0;
        foreach (var b in AnimationUtility.GetCurveBindings(src))
        {
            if (b.type != typeof(Animator) || b.path != "") continue;
            if (ex.Any(p => b.propertyName.StartsWith(p, System.StringComparison.Ordinal))) { skipped++; continue; }
            var c = AnimationUtility.GetEditorCurve(src, b);
            var old = AnimationUtility.GetEditorCurve(dst, b);
            if (old == null || c.length == 0 || old.length == 0) return $"{b.propertyName}: missing in dst, nothing written";
            if (!IsDense(c, src)) return $"{b.propertyName}: src has {c.length} keys, not one per frame; import {srcPath} with animation compression Off. nothing written";
            float s0 = c.keys[0].time, s1 = c.keys[c.length - 1].time, d0 = old.keys[0].time, d1 = old.keys[old.length - 1].time;
            if (Mathf.Abs(s0 - d0) > frame || Mathf.Abs(s1 - d1) > frame) return $"{b.propertyName}: time range differs (src {s0:F3}-{s1:F3}, dst {d0:F3}-{d1:F3}), nothing written";
            if (cl.Contains(b.propertyName))
            {
                var k = c.keys;
                for (int i = 0; i < k.Length; i++) if (k[i].value > 1f) { k[i].value = 1f; clampedKeys++; }
                c.keys = k;
            }
            keysBefore += c.length;
            c = ClipCurveTools.ReduceLinear(c, ReduceEps(b.propertyName, 0.002f));
            keysAfter += c.length;
            bindings.Add(b); curves.Add(c);
        }
        if (bindings.Count == 0) return "no curves";
        AnimationUtility.SetEditorCurves(dst, bindings.ToArray(), curves.ToArray());
        EditorUtility.SetDirty(dst);
        AssetDatabase.SaveAssets();
        return $"rebuilt {bindings.Count} curves (kept {skipped} excluded), keys {keysBefore} -> {keysAfter}, clamped keys {clampedKeys}";
    }
}
