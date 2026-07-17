// See README.md for license details.

ThisBuild / scalaVersion     := "2.13.12"
ThisBuild / version          := "0.1.0"
ThisBuild / organization     := "%ORGANIZATION%"

val chiselVersion = "7.3.0"

lazy val root = (project in file("."))
  .enablePlugins(ScapegoatSbtPlugin)
  .settings(
    name := "%NAME%",
    libraryDependencies ++= Seq(
      "org.chipsalliance" %% "chisel" % chiselVersion,
      // Override the firtool that Chisel bundles by default with a newer one.
      // firtool-resolver extracts the firtool binary from this jar at runtime.
      "org.chipsalliance" % "llvm-firtool" % "1.150.2",
      "org.scalatest" %% "scalatest" % "3.2.19" % "test",
    ),
    scalacOptions ++= Seq(
      "-language:reflectiveCalls",
      "-deprecation",
      "-feature",
      "-Xcheckinit",
      "-Ymacro-annotations",
    ),
    addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % chiselVersion cross CrossVersion.full),
    scapegoatReports := Seq("xml", "html", "markdown"),
  )
