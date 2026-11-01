# Template provenance and license handling

## Current decision

`templates/resume.tex` is a new JobBot layout under the project's 0BSD license. No third-party resume class, named template macro set, sample biography, font files or icons were copied into the skill. General typographic goals are single-column text, readable hierarchy, wrapping headings, and clear dates. This is an original implementation, not a claim that a separate clean-room legal process was performed.

It uses externally installed TeX packages/fonts, which retain their own terms. A 0BSD source license does not relicense those resources or a user's personal resume content. Do not vendor font files, icons or classes just because a repository has a permissive root license.

The template supports A4/Letter, English/Chinese section labels, and ordered work/project/research/course/activity/education/skill sections. Other languages need confirmed complete `section_labels`. English defaults to pdfLaTeX; Chinese defaults to XeLaTeX with installed `ctex`/Fandol. Optional `market.latex_engine` can select pdfLaTeX/XeLaTeX/LuaLaTeX; Chinese needs one of the latter two. Photos and multiple selectable layouts are still unimplemented.

## Future reuse

When adding an external template, record source URL, revision, exact files, file-specific terms, upstream attribution and font/icon dependencies before copying. Preserve required license/notices with the affected files. MIT permits reuse subject to its notice condition; it does not make the upstream portions 0BSD. Keep project-authored code and third-party terms explicit. Merely changing macro names or deleting a header is not an independent implementation.

Authoritative license texts: [MIT](https://opensource.org/license/mit), [0BSD](https://opensource.org/license/0bsd), [Unlicense](https://unlicense.org/), [CC0](https://creativecommons.org/publicdomain/zero/1.0/).
