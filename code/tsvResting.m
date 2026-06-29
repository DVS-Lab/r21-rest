%%**********************************************************************
%% Resting State Blink & Pupil analysis
%%**********************************************************************

% The TSV files for the resting state are divided into 4s "trials", each
% row stores (per 4 s trial) the stimulation target (which changes only per block/run), 
% the fraction of time the eyes were closed (eyeClosed), the number of
% blinks (nrBlinks) and the mean pupil size (meanPupilArea)

%% Locate r21-cardgame and kStats
scriptFile = mfilename('fullpath');
if isempty(scriptFile)
    scriptDir = pwd;
else
    scriptDir = fileparts(scriptFile);
end
candidateRoots = {getenv('R21_CARDGAME_ROOT'), ...
    '/Users/tug87422/github/r21-cardgame', ...
    '/ZPOOL/data/projects/r21-cardgame', ...
    fullfile(scriptDir,'..','..','r21-cardgame')};
dataRoot = '';
for rootNr = 1:numel(candidateRoots)
    thisRoot = candidateRoots{rootNr};
    if ~isempty(thisRoot) && exist(fullfile(thisRoot,'bids'),'dir')
        dataRoot = thisRoot;
        break;
    end
end
assert(~isempty(dataRoot), ['Could not find r21-cardgame. Set ' ...
    'R21_CARDGAME_ROOT to the folder containing the bids directory.']);

% General lab helpers live in r21-cardgame/klab. tsvRead is convenient, but
% readtable below is kept as a fallback so this script is not path-fragile.
klabCandidates = {getenv('KLAB_ROOT'), getenv('R21_KLAB_ROOT'), ...
    fullfile(dataRoot,'klab'), fullfile(scriptDir,'..','..','r21-cardgame','klab')};
for rootNr = 1:numel(klabCandidates)
    thisRoot = klabCandidates{rootNr};
    if ~isempty(thisRoot) && exist(thisRoot,'dir') && exist('tsvRead','file') ~= 2
        addpath(thisRoot);
    end
end

% This analysis uses the kStats LME toolbox. Prefer the r21-cardgame
% submodule, but allow an explicit checkout via KSTATS_ROOT.
if exist('+lm/disp.m','file') ~= 2
    kStatsCandidates = {getenv('KSTATS_ROOT'), getenv('R21_KSTATS_ROOT'), ...
        fullfile(dataRoot,'klab','kStats'), ...
        fullfile(scriptDir,'..','klab','kStats')};
    for rootNr = 1:numel(kStatsCandidates)
        thisRoot = kStatsCandidates{rootNr};
        if ~isempty(thisRoot) && exist(fullfile(thisRoot,'+lm','disp.m'),'file')
            addpath(thisRoot);
            break;
        end
    end
end
if exist('+lm/disp.m','file') ~= 2
    expectedRoot = fullfile(dataRoot,'klab','kStats');
    if exist(expectedRoot,'dir')
        error(['The kStats folder exists but does not contain +lm/disp.m: %s\n' ...
            'From r21-cardgame, run: git submodule update --init --recursive\n' ...
            'Or set KSTATS_ROOT/R21_KSTATS_ROOT to another kStats checkout.'], expectedRoot);
    end
    error(['The kStats toolbox is needed for this analysis. ' ...
        'Expected it under %s or set KSTATS_ROOT/R21_KSTATS_ROOT. ' ...
        'Repository: https://github.com/klabhub/kStats'], expectedRoot);
end

%% Read the data
subjects = [ 189   203   207   208   209   210   211   213   214   215   217   218   219   220   221   222   225   226    227   228   230   231   234   235   236   237   238];
restT=table;
for sub = subjects(:)'
    for run=1:4
       filename = sprintf('%s/bids/sub-%3d/func/sub-%3d_task-rest_run-%02d_events.tsv',dataRoot,sub,sub,run);
       if exist(filename,'file')
           try
            if exist('tsvRead','file') == 2
                thisT =tsvRead(filename);
            else
                thisT =readtable(filename,'ReadVariableNames',true, ...
                    'FileType','text','TreatAsEmpty',{'n/a','N/A'}, ...
                    'Delimiter','\t');
            end
            restT = [restT;thisT]; %#ok<AGROW>
           catch me
               disp(['Skipping ' filename  '(' me.message ')']);
           end
       end
    end
end
assert(height(restT) > 0, ['No task-rest event rows were read. Check that ' ...
    'r21-cardgame/klab is on the path or that readtable can read the TSV files.']);
assert(ismember('target',restT.Properties.VariableNames), ...
    'Task-rest event table does not contain the required target column.');
% By sorting the rows sham first, the sham condition becomes the reference
% in the anova/linear model. 
[~,shamFirst] = sort(strcmpi(restT.target,'SHAM'),'descend');
restT = restT(shamFirst,:);

%% Analyze the number of blinks 
% Use Poisson and remove outliers
outlier = isoutlier(restT.nrBlinks);
fprintf("%d outliers (%.2f%%) removed\n",sum(outlier),mean(outlier));
lmBlinks = fitglme(restT,'nrBlinks~target + (1|subjectNr)','Distribution','Poisson','Exclude',outlier)
lm.disp(lmBlinks)
GBlinks=groupsummary(restT,'target','mean','nrBlinks')
blinksPerSubject = lm.plotPerSubject(lmBlinks); % Check consistency across subjects
blinksPerSubject = rows2vars(blinksPerSubject);
[rBlinks,pBlinks]  = corrcoef(blinksPerSubject{:,"target_" +["RTPJ" "BOTH" "VLPFC"]},'Rows','pairwise')

%% Analyze the pupil size
% Use normal distribution, and remove outliers.
outlier = isoutlier(restT.meanPupilArea);
fprintf("%d outliers (%.2f%%) removed\n",sum(outlier),mean(outlier));
lmPa = fitlme(restT,'meanPupilArea~target + (1|subjectNr)','Exclude',outlier)
lm.disp(lmPa,'*','RANDOMSTD');% Show effects as a percentage of the grand mean pupil size
GPa=groupsummary(restT,'target','mean','meanPupilArea')
paPerSubject  = lm.plotPerSubject(lmPa);
paPerSubject = rows2vars(paPerSubject);
[rPa,pPa]  = corrcoef(paPerSubject{:,"target_" +["RTPJ" "BOTH" "VLPFC"]},'Rows','pairwise')


%% Summary
% Both the number of blinks and the mean pupil size are affected by
% stimulation target. Mean pupil area and the number of blinks are smallest 
% in the sham condition, inconsistent with an explanation based on phosphenes.
%
% Although the p-values are small, the sign of the effects are not  consistent
% across subjects (pretty much 50/50). On the other hand, most subjects
% have individually signficant effects and these are correlated across
% targets.
